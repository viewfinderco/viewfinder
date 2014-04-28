{
  'xcode_settings': {
    'IPHONEOS_DEPLOYMENT_TARGET': '6.0',
    'SDKROOT': 'iphoneos',
    # Tell Xcode not to install header files for libraries when generating the
    # archive for submission to the app store.
    'SKIP_INSTALL': 'YES',
    # Specify -fvisibility=hidden so that shared libraries cannot see symbols
    # defined by the Viewfinder app. This is necessary protection for users
    # running Viewfinder on jailbroken phones which can inject arbitrary
    # libraries and code into the Viewfinder address space. In particular, the
    # TypeStatus extension causes libprotobuf.dylib to be loaded which has
    # symbols which collide with our copy of libprotobuf. Note that we can't
    # directly use libprotobuf.dylib as it is considered a private library by
    # Apple.
    'GCC_SYMBOLS_PRIVATE_EXTERN' : 'YES',
    'CLANG_CXX_LANGUAGE_STANDARD' : 'c++11',
    'CLANG_CXX_LIBRARY' : 'libc++',
  },
  'configurations': {
    'Debug': {
      'xcode_settings': {
        'GCC_OPTIMIZATION_LEVEL': '0',
        'ONLY_ACTIVE_ARCH': 'YES',
      },
    },
  },
  'target_defaults': {
    'configurations': {
      'Debug': {
        'xcode_settings': {
          # Xcode settings can be specified at both the project and target level; xcode gives a warning
          # if ONLY_ACTIVE_ARCH is not set at both levels for the "Debug" configuration.
          'ONLY_ACTIVE_ARCH': 'YES',
        },
      },
      'Release': {},
      'Ad-hoc': {},
      'AppStore': {},
      'Enterprise': {},
    },
  },
}
