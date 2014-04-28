// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault.

#import <chrono>
#import <iomanip>
#import <map>
#import <thread>
#import <cxxabi.h>
#import <dlfcn.h>
#import <unwind.h>
#import "Logging.h"
#import "Mutex.h"
#import "Utils.android.h"
#import "Utils.h"

namespace {

// We have 3 queues, the "main" queue, the "network" queue and the "priority"
// queue. The "main" and "network" queues only contain a single thread.
enum {
  QUEUE_MAIN,
  QUEUE_NETWORK,
  QUEUE_CONCURRENT,
  QUEUE_TYPES,
};

// Within each queue, blocks are scheduled in strict priority order. That is,
// all blocks at PRIORITY_HIGH are run before all blocks at PRIORITY_LOW.
enum {
  PRIORITY_HIGH,
  PRIORITY_LOW,
  PRIORITY_BACKGROUND,
};

class ThreadDispatch {
  // We maintain two maps for each queue. The ReadyMap is keyed by <priority,
  // sequence>. The PendingMap is keyed by <timestamp, priority,
  // sequence>. When a block is ready to run, it is moved from PendingMap to
  // ReadyMap where timestamp is ignored. This allows a high priority block
  // scheduled shortly after a low priority block to be run before the low
  // priority block.
  typedef std::pair<int, int64_t> ReadyKey;
  typedef std::pair<double, ReadyKey> PendingKey;
  typedef std::map<ReadyKey, DispatchBlock> ReadyMap;
  typedef std::map<PendingKey, DispatchBlock> PendingMap;

  struct Thread {
    Thread(int i)
        : id(i),
          thread(NULL) {
    }
    ~Thread() {
      delete thread;
    }
    const int id;
    std::thread* thread;
  };

  struct Queue {
    Queue(const string& n, int c)
        : name(n),
          concurrency(c),
          sequence(0),
          thread_id(0) {
    }
    const string name;
    const int concurrency;
    Mutex mu;
    ReadyMap ready;
    PendingMap pending;
    int64_t sequence;
    int thread_id;
    std::set<Thread*> threads;
  };

 public:
  ThreadDispatch(JavaVM* jvm)
      : jvm_(jvm),
        queues_(QUEUE_TYPES, NULL) {
    queues_[QUEUE_MAIN] = new Queue("main", 1);
    queues_[QUEUE_NETWORK] = new Queue("network", 1);
    queues_[QUEUE_CONCURRENT] = new Queue("concurrent", 3);
  }

  bool IsMainThread() const {
    // TODO(peter): We could replace this junk with a thread local which stores
    // the queue type.
    Queue* const q = queues_[QUEUE_MAIN];
    if (q->threads.empty()) {
      return false;
    }
    Thread* const t = *q->threads.begin();
    // LOG("IsMainThread: %d", int(t->thread->get_id() == std::this_thread::get_id()));
    return t->thread->get_id() == std::this_thread::get_id();
  }

  void Run(int type, int priority, double delay, const DispatchBlock& block) {
    Queue* const q = queues_[type];
    MutexLock l(&q->mu);
    // LOG("%s: queueing: %d %.3f", q->name, priority, delay);
    const ReadyKey ready_key(priority, q->sequence++);
    if (delay <= 0) {
      q->ready[ready_key] = block;
    } else {
      const PendingKey pending_key(WallTime_Now() + delay, ready_key);
      q->pending[pending_key] = block;
    }

    if (q->threads.size() < q->concurrency) {
      Thread* t = new Thread(q->thread_id++);
      // LOG("%s/%d: starting thread", q->name, t->id);
      q->threads.insert(t);
      t->thread = new std::thread([this, q, t]() {
          ThreadLoop(q, t);
        });
    }
  }

  void ThreadLoop(Queue* q, Thread* t) {
    JNIEnv* env;
    // TODO(peter): check return status.
    jvm_->AttachCurrentThread(&env, NULL);

    q->mu.Lock();

    for (;;) {
      // LOG("%s/%d: looping: %d/%d",
      //     q->name, t->id, q->ready.size(), q->pending.size());

      // Loop over the pending blocks and move them to the ready map.
      const WallTime now = WallTime_Now();
      while (!q->pending.empty()) {
        auto it = q->pending.begin();
        const PendingKey& key = it->first;
        if (key.first > now) {
          break;
        }
        // The block is ready to run, move it to the ready queue.
        // LOG("%s/%d: ready: %d", q->name, t->id, key.second.second);
        q->ready[key.second].swap(it->second);
        q->pending.erase(it);
      }

      if (!q->ready.empty()) {
        // A block is ready to run. Run it.
        auto it = q->ready.begin();
        const int64_t seq = it->first.second;
        DispatchBlock block;
        block.swap(it->second);
        // LOG("%s/%d: running block: %d", q->name, t->id, seq);
        q->ready.erase(it);
        q->mu.Unlock();
        block();
        q->mu.Lock();
        // We ran a block, which might have taken a non-trivial amount of
        // time. Restart the loop in order to recheck whether any pending
        // blocks have become ready blocks.
        continue;
      }

      // No blocks were ready to run and we've already checked that the first
      // pending block (if one exists) is not ready. Wait for something to do.
      if (!q->pending.empty()) {
        auto it = q->pending.begin();
        const PendingKey& key = it->first;
        const double wait_time  = key.first - now;
        const int64_t seq = key.second.first;
        // The next block to run will be ready to run in "wait_time"
        // seconds. Wait for that amount of time, or until the sequence number
        // of the first block on the queue has changed.
        // LOG("%s/%d: waiting: %d %.3f", q->name, t->id, seq, wait_time);
        q->mu.TimedWait(wait_time, [q, seq]() {
            if (!q->ready.empty()) {
              return true;
            }
            if (q->pending.empty()) {
              return false;
            }
            const PendingKey& key = q->pending.begin()->first;
            return key.second.first != seq;
          });
      } else {
        // Both queues are empty, wait until we have a block to run.
        q->mu.Wait([q]() {
            return !q->ready.empty() || !q->pending.empty();
          });
      }
    }

    q->mu.Unlock();

    // Threads need to be detached before terminating.
    jvm_->DetachCurrentThread();
  }

 private:
  JavaVM* const jvm_;
  vector<Queue*> queues_;
};

ThreadDispatch* dispatch;

struct StackCrawlState {
  BacktraceData* data;
  int ignore;
};

_Unwind_Reason_Code BacktraceFunction(_Unwind_Context* context, void* arg) {
  StackCrawlState* state = reinterpret_cast<StackCrawlState*>(arg);
  BacktraceData* data = state->data;
  const uintptr_t ip = _Unwind_GetIP(context);
  if (ip) {
    if (state->ignore) {
      state->ignore--;
    } else {
      data->callstack[data->frames++] = (void*)ip;
      if (data->frames >= ARRAYSIZE(data->callstack)) {
        return _URC_END_OF_STACK;
      }
    }
  }
  return _URC_NO_REASON;
}

}  // namespace

string app_version;
std::function<int64_t ()> free_disk_space;
std::function<int64_t ()> total_disk_space;

void InitDispatch(JavaVM* jvm) {
  CHECK(!dispatch);
  dispatch = new ThreadDispatch(jvm);
}

string AppVersion() {
  return app_version;
}

int64_t FreeDiskSpace() {
  if (!free_disk_space) {
    return 0;
  }
  return free_disk_space();
}

int64_t TotalDiskSpace() {
  if (!total_disk_space) {
    return 0;
  }
  return total_disk_space();
}

bool dispatch_is_main_thread() {
  return dispatch->IsMainThread();
}

void dispatch_main(const DispatchBlock& block) {
  return dispatch->Run(QUEUE_MAIN, 0, 0, block);
}

void dispatch_main_async(const DispatchBlock& block) {
  return dispatch->Run(QUEUE_MAIN, 0, 0, block);
}

void dispatch_network(const DispatchBlock& block) {
  return dispatch->Run(QUEUE_NETWORK, 0, 0, block);
}

void dispatch_high_priority(const DispatchBlock& block) {
  return dispatch->Run(QUEUE_CONCURRENT, PRIORITY_HIGH, 0, block);
}

void dispatch_low_priority(const DispatchBlock& block) {
  return dispatch->Run(QUEUE_CONCURRENT, PRIORITY_LOW, 0, block);
}

void dispatch_background(const DispatchBlock& block) {
  return dispatch->Run(QUEUE_CONCURRENT, PRIORITY_BACKGROUND, 0, block);
}

void dispatch_after_main(double delay, const DispatchBlock& block) {
  return dispatch->Run(QUEUE_MAIN, 0, delay, block);
}

void dispatch_after_network(double delay, const DispatchBlock& block) {
  return dispatch->Run(QUEUE_NETWORK, 0, delay, block);
}

void dispatch_after_high_priority(double delay, const DispatchBlock& block) {
  return dispatch->Run(QUEUE_CONCURRENT, PRIORITY_HIGH, delay, block);
}

void dispatch_after_low_priority(double delay, const DispatchBlock& block) {
  return dispatch->Run(QUEUE_CONCURRENT, PRIORITY_LOW, delay, block);
}

void dispatch_after_background(double delay, const DispatchBlock& block) {
  return dispatch->Run(QUEUE_CONCURRENT, PRIORITY_BACKGROUND, delay, block);
}

ostream& operator<<(ostream& os, const BacktraceData& bt) {
  Dl_info info;
  for (int i = 0; i < bt.frames; ++i) {
    // The format of each line is intended to match the Android dump format:
    //
    //   #<frame> pc <address-within-library> <library-name> (<symbol>)
    if (!dladdr(bt.callstack[i], &info)) {
      continue;
    }
    os << "#" << std::setw(2) << std::setfill('0') << i << " pc ";
    os << std::hex << std::setw(8) << std::setfill('0') << std::noshowbase
       << reinterpret_cast<ptrdiff_t>(
           reinterpret_cast<const char*>(bt.callstack[i]) -
           reinterpret_cast<const char*>(info.dli_fbase));
    if (info.dli_fname) {
      os << " " << info.dli_fname;
    }
    if (info.dli_sname) {
      os << " (";
      int status = 0;
      char* demangled = abi::__cxa_demangle(info.dli_sname, NULL, NULL, &status);
      if (demangled) {
        os << demangled;
        free(demangled);
      } else {
        os << info.dli_sname;
      }
      os << ")";
    }
    os << "\n";
  }
  return os;
}

BacktraceData Backtrace() {
  BacktraceData d;
  d.frames = 0;
#if !defined(__arm__)
  // TODO(peter): This doesn't currently work on arm builds because we can't
  // find the _Unwind_GetIP symbol!
  StackCrawlState state;
  state.ignore = 1;
  state.data = &d;
  _Unwind_Backtrace(BacktraceFunction, &state);
#endif  // !defined(__arm__)
  return d;
}
