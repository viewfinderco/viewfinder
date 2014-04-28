// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_STL_UTILS_H
#define VIEWFINDER_STL_UTILS_H

#import <set>
#import <map>
#import <google/protobuf/repeated_field.h>
#import <unordered_map>
#import <unordered_set>
#import <type_traits>
#import <vector>
#import "Utils.h"

typedef std::unordered_set<string> StringSet;
typedef std::unordered_map<string, string> StringMap;

struct ContainerLiteralMaker {
  template <int N, typename A>
  struct Maker {
    Maker() {
    }
    Maker(A a0) {
      args_[0] = a0;
    }
    Maker(A a0, A a1) {
      args_[0] = a0;
      args_[1] = a1;
    }
    Maker(A a0, A a1, A a2) {
      args_[0] = a0;
      args_[1] = a1;
      args_[2] = a2;
    }
    Maker(A a0, A a1, A a2, A a3) {
      args_[0] = a0;
      args_[1] = a1;
      args_[2] = a2;
      args_[3] = a3;
    }
    Maker(A a0, A a1, A a2, A a3, A a4) {
      args_[0] = a0;
      args_[1] = a1;
      args_[2] = a2;
      args_[3] = a3;
      args_[4] = a4;
    }
    Maker(A a0, A a1, A a2, A a3, A a4, A a5) {
      args_[0] = a0;
      args_[1] = a1;
      args_[2] = a2;
      args_[3] = a3;
      args_[4] = a4;
      args_[5] = a5;
    }
    Maker(A a0, A a1, A a2, A a3, A a4, A a5, A a6) {
      args_[0] = a0;
      args_[1] = a1;
      args_[2] = a2;
      args_[3] = a3;
      args_[4] = a4;
      args_[5] = a5;
      args_[6] = a6;
    }
    Maker(A a0, A a1, A a2, A a3, A a4, A a5, A a6, A a7) {
      args_[0] = a0;
      args_[1] = a1;
      args_[2] = a2;
      args_[3] = a3;
      args_[4] = a4;
      args_[5] = a5;
      args_[6] = a6;
      args_[7] = a7;
    }
    Maker(A a0, A a1, A a2, A a3, A a4, A a5, A a6, A a7, A a8) {
      args_[0] = a0;
      args_[1] = a1;
      args_[2] = a2;
      args_[3] = a3;
      args_[4] = a4;
      args_[5] = a5;
      args_[6] = a6;
      args_[7] = a7;
      args_[8] = a8;
    }
    Maker(A a0, A a1, A a2, A a3, A a4, A a5, A a6, A a7, A a8, A a9) {
      args_[0] = a0;
      args_[1] = a1;
      args_[2] = a2;
      args_[3] = a3;
      args_[4] = a4;
      args_[5] = a5;
      args_[6] = a6;
      args_[7] = a7;
      args_[8] = a8;
      args_[9] = a9;
    }

    template <typename T>
    operator std::set<T>() const {
      return std::set<T>(&args_[0], &args_[N]);
    }

    template <typename T>
    operator std::unordered_set<T>() const {
      return std::unordered_set<T>(&args_[0], &args_[N]);
    }

    template <typename T>
    operator std::vector<T>() const {
      return std::vector<T>(&args_[0], &args_[N]);
    }

    A args_[N];
  };

  template <typename A>
  Maker<1, A> operator()(A a0) const {
    return Maker<1, A>(a0);
  }

  template <typename A>
  Maker<2, A> operator()(A a0, A a1) const {
    return Maker<2, A>(a0, a1);
  }

  template <typename A>
  Maker<3, A> operator()(A a0, A a1, A a2) const {
    return Maker<3, A>(a0, a1, a2);
  }

  template <typename A>
  Maker<4, A> operator()(A a0, A a1, A a2, A a3) const {
    return Maker<4, A>(a0, a1, a2, a3);
  }

  template <typename A>
  Maker<5, A> operator()(A a0, A a1, A a2, A a3, A a4) const {
    return Maker<5, A>(a0, a1, a2, a3, a4);
  }

  template <typename A>
  Maker<6, A> operator()(A a0, A a1, A a2, A a3, A a4, A a5) const {
    return Maker<6, A>(a0, a1, a2, a3, a4, a5);
  }

  template <typename A>
  Maker<7, A> operator()(A a0, A a1, A a2, A a3, A a4, A a5, A a6) const {
    return Maker<7, A>(a0, a1, a2, a3, a4, a5, a6);
  }

  template <typename A>
  Maker<8, A> operator()(
      A a0, A a1, A a2, A a3, A a4, A a5, A a6, A a7) const {
    return Maker<8, A>(a0, a1, a2, a3, a4, a5, a6, a7);
  }

  template <typename A>
  Maker<9, A> operator()(
      A a0, A a1, A a2, A a3, A a4, A a5, A a6, A a7, A a8) const {
    return Maker<9, A>(a0, a1, a2, a3, a4, a5, a6, a7, a8);
  }

  template <typename A>
  Maker<10, A> operator()(
      A a0, A a1, A a2, A a3, A a4, A a5, A a6, A a7, A a8, A a9) const {
    return Maker<10, A>(a0, a1, a2, a3, a4, a5, a6, a7, a8, a9);
  }
};

extern const ContainerLiteralMaker& ContainerLiteral;
extern const ContainerLiteralMaker& L;

template <typename T, typename K>
inline const typename T::mapped_type FindOrNull(
    const T& container, const K& key) {
  typedef typename T::const_iterator const_iterator;
  const_iterator iter(container.find(key));
  if (iter == container.end()) {
    return NULL;
  }
  return iter->second;
}

template <typename T, typename K>
inline typename T::mapped_type FindOrNull(
    T* container, const K& key) {
  typedef typename T::iterator iterator;
  iterator iter(container->find(key));
  if (iter == container->end()) {
    return NULL;
  }
  return iter->second;
}

template <typename T, typename K>
inline const typename T::mapped_type* FindPtrOrNull(
    const T& container, const K& key) {
  typedef typename T::const_iterator const_iterator;
  const_iterator iter(container.find(key));
  if (iter == container.end()) {
    return NULL;
  }
  return &iter->second;
}

template <typename T, typename K>
inline typename T::mapped_type* FindPtrOrNull(T* container, const K& key) {
  typedef typename T::iterator iterator;
  iterator iter(container->find(key));
  if (iter == container->end()) {
    return NULL;
  }
  return &iter->second;
}

template <typename T, typename K>
inline const typename T::mapped_type FindOrDefault(
    const T& container, const K& key,
    const typename T::mapped_type& def_value) {
  typedef typename T::const_iterator const_iterator;
  const_iterator iter(container.find(key));
  if (iter == container.end()) {
    return def_value;
  }
  return iter->second;
}

template <typename T, typename K>
inline bool ContainsKey(const T& container, const K& key) {
  return container.find(key) != container.end();
}

#ifdef __OBJC__

template <typename T>
inline void DeletePointer(T* value, std::true_type is_nsobject) {
}

template <typename T>
inline void DeletePointer(T* value, std::false_type is_nsobject) {
  delete value;
}

#endif // __OBJC__

template <typename T>
inline void DeleteValue(T& value) {
  // Value isn't a pointer. Nothing to do.
}

template <typename T>
inline void DeleteValue(T* value) {
#ifdef __OBJC__
  typedef typename std::is_convertible<T*, id>::type is_nsobject;
  DeletePointer(value, is_nsobject());
#else // __OBJC__
  delete value;
#endif // __OBJC__
}

template <typename F, typename S>
inline void DeleteValue(std::pair<F, S>& p) {
  DeleteValue(p.first);
  DeleteValue(p.second);
}

template <typename T>
inline void Clear(T* container) {
  if (!container) {
    return;
  }
  for (typename T::iterator iter(container->begin());
       iter != container->end();
       ++iter) {
    DeleteValue(*iter);
  }
  container->clear();
}

// Remove an element from a protobuf repeated field.  Reorders existing elements (the last element is
// moved to the newly-vacated position) and changes the size of the array.
template <typename T>
void ProtoRepeatedFieldRemoveElement(google::protobuf::RepeatedPtrField<T>* array, int i) {
  array->SwapElements(i, array->size() - 1);
  array->RemoveLast();
}

template <typename T>
bool SetsIntersect(const std::set<T>& a, const std::set<T>& b) {
  // TODO(ben): it would be more efficient to implement this by hand
  // since we don't care about actually accumulating the results.
  std::set<T> result;
  std::set_intersection(
      a.begin(), a.end(), b.begin(), b.end(),
      std::insert_iterator<std::set<T> >(result, result.end()));
  return !result.empty();
}

template <typename T, typename K>
int IndexOf(const T& container, const K& key) {
  typename T::const_iterator iter =
      std::find(container.begin(), container.end(), key);
  if (iter == container.end()) {
    return -1;
  }
  return std::distance(container.begin(), iter);
}

template <typename I>
inline ostream& Output(ostream& os, I begin, I end) {
  os << "<";
  for (I iter(begin); iter != end; ++iter) {
    if (iter != begin) {
      os << " ";
    }
    os << *iter;
  }
  os << ">";
  return os;
}

template <int N, typename A>
inline ostream& operator<<(
    ostream& os, const ContainerLiteralMaker::Maker<N, A>& m) {
  os << "<";
  for (int i = 0; i < N; ++i) {
    if (i > 0) {
      os << " ";
    }
    os << m.args_[i];
  }
  os << ">";
  return os;
}

namespace std {

template <typename F, typename S>
inline ostream& operator<<(ostream& os, const pair<F,S>& p) {
  os << p.first << ":" << p.second;
  return os;
}

template <typename T>
inline ostream& operator<<(ostream& os, const vector<T>& v) {
  return Output(os, v.begin(), v.end());
}

template <typename T, typename C>
inline ostream& operator<<(ostream& os, const set<T, C>& s) {
  return Output(os, s.begin(), s.end());
}

template <typename K, typename V, typename C>
inline ostream& operator<<(ostream& os, const map<K, V, C>& m) {
  return Output(os, m.begin(), m.end());
}

template <typename T, typename H, typename E>
inline ostream& operator<<(ostream& os, const unordered_set<T, H, E>& s) {
  return Output(os, s.begin(), s.end());
}

template <typename K, typename V, typename H, typename E>
inline ostream& operator<<(ostream& os, const unordered_map<K, V, H, E>& m) {
  return Output(os, m.begin(), m.end());
}

}  // namespace std

#ifdef __OBJC__

// The libc++ hash<T*> specialization doesn't work for objective-c
// types. Provide our own specialization that does.
struct HashObjC : public std::unary_function<id, size_t> {
  size_t operator()(id v) const {
    return std::hash<void*>()((__bridge void*)v);
  }
};

#endif  // __OBJC__

#endif // VIEWFINDER_STL_UTILS_H
