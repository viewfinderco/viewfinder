// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.
//
// TODO(pmattis): %|spec| item specifier

#import <algorithm>
#import "Format.h"
#import "Logging.h"

namespace {

using std::ios_base;
using std::min;

struct State {
  State(ostream& o, const string& format,
        const Formatter::Arg* const* a, int count)
      : os(o),
        ptr(format.data()),
        end(ptr + format.size()),
        args(a),
        args_count(count),
        num_args(0),
        cur_arg(0) {
  }

  ostream& os;
  const char* ptr;
  const char* const end;
  const Formatter::Arg* const* args;
  const int args_count;
  int num_args;
  int cur_arg;
};

struct Item {
  Item()
      : fill(' '),
        space_pad(false),
        truncate(false),
        width(0),
        extra_width(0),
        precision(6),
        flags(ios_base::dec) {
  }

  char fill;
  bool space_pad;
  bool truncate;
  int width;
  int extra_width;
  int precision;
  ios_base::fmtflags flags;
};

void PutItem(State* s, const Item& i) {
  // TODO(pmattis): Handle positional arguments.
  const int width =
      (i.width >= 0) ? i.width : s->args[s->cur_arg++]->AsInt();
  const int precision =
      (i.precision >= 0) ? i.precision : s->args[s->cur_arg++]->AsInt();

  if (i.truncate || i.space_pad) {
    // Truncation or space padding required, output to a string and
    // truncate the result.
    const int max_width =
        (i.truncate ? precision + i.extra_width : 0);
    std::ostringstream ss;
    ss.fill(i.fill);
    ss.width(max_width);
    ss.precision(6);
    ss.flags((i.flags & ~ios_base::adjustfield) |
             ios_base::internal);
    s->args[s->cur_arg++]->Put(ss);
    s->os.fill(' ');
    s->os.width(width);
    s->os.flags(i.flags);
    const string& str = ss.str();
    if (i.space_pad && !str.empty() && str[0] == '+') {
      s->os.write(" ", 1);
      s->os << str.substr(1, max_width - 1);
    } else {
      s->os << str.substr(0, max_width);
    }
  } else {
    // No truncation required, output directly to stream.
    s->os.fill(i.fill);
    s->os.width(width);
    s->os.precision(precision);
    s->os.flags(i.flags);
    s->args[s->cur_arg++]->Put(s->os);
  }
}

const char* ParseInt(const char* start, int *value) {
  char* end;
  *value = strtol(start, &end, 10);
  return end;
}

bool ProcessDirective(State* s) {
  const char* const start = s->ptr;
  bool parsed_precision = false;
  Item i;

  // Parse flags.
  while (++s->ptr < s->end) {
    switch (*s->ptr) {
      case '#':
        i.flags |= ios_base::showbase;
        i.flags |= ios_base::showpoint;
        i.flags |= ios_base::boolalpha;
        break;
      case '0':
        i.fill = '0';
        break;
      case '-':
        i.flags &= ~ios_base::adjustfield;
        i.flags |= ios_base::left;
        break;
      case '_':
        i.flags &= ~ios_base::adjustfield;
        i.flags |= ios_base::internal;
        break;
      case ' ':
        if (!(i.flags & ios_base::showpos)) {
          i.space_pad = true;
          i.flags |= ios_base::showpos;
        }
        break;
      case '+':
        i.space_pad = false;
        i.flags |= ios_base::showpos;
        break;
      default:
        goto parse_width;
    }
  }
  goto error;

parse_width:
  if (*s->ptr == '*') {
    i.width = -1;
    ++s->ptr;
  } else if (isdigit(*s->ptr)) {
    s->ptr = ParseInt(s->ptr, &i.width);
    if (s->ptr >= s->end) {
      goto error;
    }
  }

  // parse_precision:
  if (*s->ptr == '.') {
    if (++s->ptr >= s->end) {
      goto error;
    }
    if (*s->ptr == '*') {
      i.precision = -1;
      ++s->ptr;
    } else if (isdigit(*s->ptr)) {
      s->ptr = ParseInt(s->ptr, &i.precision);
      if (s->ptr >= s->end) {
        goto error;
      }
    }
    parsed_precision = true;
  }

  // done:
  switch (*s->ptr) {
    case 'u':
      i.space_pad = false;
      i.flags &= ~ios_base::showpos;
    case 'd':
    case 'i':
      i.flags &= ~ios_base::basefield;
      i.flags |=  ios_base::dec;
      if (parsed_precision) {
        i.truncate = true;
        i.fill = '0';
        if (i.flags & ios_base::showpos) {
          i.extra_width = 1;
        }
      }
      break;

    case 'X':
      i.flags |= ios_base::uppercase;
    case 'p':
    case 'x':
      i.flags &= ~ios_base::basefield;
      i.flags |= ios_base::hex;
      if (parsed_precision) {
        i.truncate = true;
        i.fill = '0';
        if (i.flags & ios_base::showbase) {
          i.extra_width = 2;
        }
      }
      break;

    case 'o':
      i.flags &= ~ios_base::basefield;
      i.flags |=  ios_base::oct;
      if (parsed_precision) {
        i.truncate = true;
        i.fill = '0';
        if (i.flags & ios_base::showbase) {
          i.extra_width = 1;
        }
      }
      break;

    case 'f':
      i.flags &= ~ios_base::floatfield;
      i.flags |=  ios_base::fixed;
      i.flags &= ~ios_base::basefield;
      i.flags |=  ios_base::dec;
      break;

    case 'E':
      i.flags |=  ios_base::uppercase;
    case 'e':
      i.flags &= ~ios_base::floatfield;
      i.flags |=  ios_base::scientific;
      i.flags &= ~ios_base::basefield;
      i.flags |=  ios_base::dec;
      break;

    case 'G':
      i.flags |= ios_base::uppercase;
    case 'g':
      i.flags &= ~ios_base::floatfield;
      i.flags &= ~ios_base::basefield;
      i.flags |=  ios_base::dec;
      break;

    case 'C':
    case 'c':
      i.truncate = true;
      i.precision = 1;
      break;

    case 'S':
    case 's':
    case '@':
      if (parsed_precision) {
        i.truncate = true;
      }
      break;

    case 'n' :
      // TODO(pmattis)
      break;

    default:
      goto error;
  }

  if (i.flags & ios_base::left) {
    if (!i.truncate) {
      // Left alignment (pad on right) and no truncation specification implies
      // pad with spaces.
      i.fill = ' ';
    }
  } else if (i.fill != ' ') {
    // Non-left alignment and non-space padding, convert to internal padding.
    i.flags = i.flags & ~ios_base::adjustfield;
    i.flags |= ios_base::internal;
  }

  ++s->ptr;

  s->num_args += 1 + (i.width == -1) + (i.precision == -1);
  if (s->num_args > s->args_count) {
    return false;
  }

  PutItem(s, i);
  return true;

error:
#ifdef DEBUG
  DIE("Error: unterminated format: ", Slice(start, s->ptr - start));
#else // DEBUG
  s->os << "<Error: unterminated format: '"
        << Slice(start, s->ptr - start) << "'>";
#endif // DEBUG
  return false;
}

}  // namespace

const FormatMaker& Format = *(new FormatMaker);

void Formatter::Apply(
    ostream& os, const Arg* const* args, int args_count) const {
  State s(os, format_, args, args_count);
  const char* last = s.ptr;
  while (s.ptr < s.end) {
    s.ptr = std::find(s.ptr, s.end, '%');
    if (s.ptr == s.end) {
      break;
    }
    os.write(last, s.ptr - last);
    if (&s.ptr[1] < s.end && s.ptr[1] == '%') {
      last = s.ptr + 1;
      s.ptr += 2;
      continue;
    }
    if (!ProcessDirective(&s)) {
      break;
    }
    last = s.ptr;
  }

  if (s.args_count != s.num_args) {
#ifdef DEBUG
    DIE("Error: incorrect number of format arguments: %d != %d",
        s.args_count, s.num_args);
#else // DEBUG
    os << "<Error: incorrect number of format arguments: "
       << s.args_count << " != " << s.num_args
       << ">";
#endif // DEBUG
    return;
  }

  os.write(last, s.end - last);
}

string Formatter::DebugString(const Arg* const* args, int args_count) const {
  std::ostringstream ss;
  ss << format_;
  for (int i = 0; i < args_count; ++i) {
    ss << " % ";
    args[i]->Put(ss);
  }
  return ss.str();
}
