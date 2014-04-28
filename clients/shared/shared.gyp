{
  # TODO(ben): why is this boilerplate necessary in every gyp file that uses protos?
  'target_defaults': {
    'default_configuration': 'Debug',
    'configurations': {
      # TODO(peter): Share these defines with ViewfinderGyp.gyp.
      'Debug': {
        'defines': [
          'DEBUG=1',
          'TESTING=1',
          'DEVELOPMENT=1',
        ],
      },
      'Release': {
        'defines': [
          'APPSTORE=1',
          'DEVELOPMENT=1',
        ],
      },
      'Ad-hoc': {
        'defines': [
          'ADHOC=1',
        ],
      },
      'AppStore': {
        'defines': [
          'APPSTORE=1',
        ],
      },
      'Enterprise': {
        'defines': [
          'APPSTORE=1',
          'ENTERPRISE=1',
        ],
      },
    },
  },
  'targets': [
    {
      'target_name': 'libshared_base',
      'type': 'static_library',
      'includes': [
        'protoc.gypi',
      ],
      'actions': [
        {
          'action_name': 'developer-defines',
          'inputs': [],
          'outputs': [
            '${INTERMEDIATE_DIR}/ALWAYS-RUN',
            '${SHARED_INTERMEDIATE_DIR}/DeveloperDefines.h',
            '${SHARED_INTERMEDIATE_DIR}/TestDefines.h',
          ],
          'action': ['bash', 'scripts/developer-defines-gyp.sh'],
        },
      ],
      'dependencies': [
        '../../third_party/shared/jsoncpp.gyp:libjsoncpp',
        '../../third_party/shared/leveldb.gyp:libleveldb',
        '../../third_party/shared/icu.gyp:icui18n',
        '../../third_party/shared/icu.gyp:icuuc',
        '../../third_party/shared/icu.gyp:icudata',
        '../../third_party/shared/phonenumbers.gyp:libphonenumbers',
        '../../third_party/shared/protobuf.gyp:libprotobuf',
        '../../third_party/shared/re2.gyp:libre2',
        '../../third_party/shared/snappy.gyp:libsnappy',
      ],
      'sources': [
        '<!@(ls *.cc)',
        '<!@(ls *.proto)',
      ],
      'conditions': [
        [ 'OS=="ios"', {
            'sources/': [
              ['exclude', '\\.android\\.cc$'],
            ],
          },
        ],
      ],
      'include_dirs': [
        '${SHARED_INTERMEDIATE_DIR}',
      ],
      'defines': [
        'OS_IOS',
        # Beginning in iOS 6, certain types (specifically dispatch_queue_t) can be either objc-based
        # (managed by ARC) or C-based (managed by explicit retain/release functions).  This causes problems
        # if use of these types occurs in both objc++ and c++ files.  This define forces the C-style semantics
        # even in .mm files.
        'OS_OBJECT_USE_OBJC=0',
      ],
      'all_dependent_settings': {
        'include_dirs': [
          '.',
          '${SHARED_INTERMEDIATE_DIR}',
        ],
        'defines': [
          'OS_IOS',
          'OS_OBJECT_USE_OBJC=0',
        ],
        'xcode_settings': {
          'CLANG_ENABLE_OBJC_ARC': 'YES',
          # Force objc++ compilation for C++ source files in dependent
          # libraries in order to avoid problems with one-definition-rule
          # violations of blocks stored in C++ data structures. We only
          # guarantee that C++ does not use blocks with the libshared_base
          # library which specifies the "-fno-blocks" compilation flag.
          'OTHER_CPLUSPLUSFLAGS': '-x objective-c++',
        },
      },
      'xcode_settings': {
        'OTHER_CPLUSPLUSFLAGS': '-fno-blocks',
      },
    },
    {
      # We need a separate target for compiling objective-c++ code in which
      # blocks are not disabled.
      'target_name': 'libshared',
      'type': 'static_library',
      'dependencies': [ 'libshared_base' ],
      'sources': [ '<!@(ls *.mm)', ],
    },
  ],
}
