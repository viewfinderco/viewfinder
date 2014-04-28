{
  'targets': [
    {
      'target_name': 'viewfinder',
      'type': 'shared_library',
      'include_dirs': [
        '../../../third_party/shared/leveldb/include/',
        '../../../third_party/shared/leveldb/',
        '../../../third_party/shared/protobuf/src/',
        '../../../third_party/shared/protobuf/',
        '../../../third_party/shared/re2/',
        '../../../third_party/shared/icu',
        '../../../third_party/shared/icu/source/common',
        '../../../third_party/shared/icu/source/i18n',
        '../../../third_party/shared/icu/source/tools/tzcode',
        '../../../third_party/shared/phonenumbers/cpp/src',

        '../gen/',
      ],
      'dependencies': [
        '../../../third_party/shared/leveldb.gyp:libleveldb',
        '../../../third_party/shared/protobuf.gyp:libprotobuf',
        '../../../third_party/shared/snappy.gyp:libsnappy',
        '../../../third_party/shared/re2.gyp:libre2',
        '../../../third_party/shared/icu.gyp:icui18n',
        '../../../third_party/shared/icu.gyp:icuuc',
        '../../../third_party/shared/icu.gyp:icudata',
        '../../../third_party/shared/phonenumbers.gyp:libphonenumbers',
        '../../shared/shared.android.gyp:libshared',
        '../../shared/shared.android.gyp:sharedprotos',
      ],
      'defines': [
        'LEVELDB_PLATFORM_ANDROID',
        'LEVELDB_PLATFORM_POSIX',
      ],
      'sources': [
        'DayTableEnv.cc',
        'DBMigrationAndroid.cc',
        'NativeAppState.cc',
        'NetworkManagerAndroid.cc',
      ],
      'cppflags': [
        '-pthread',
      ],
      'ldflags': [
        '-lz',
        '-llog',
      ],
    },
  ],
}
