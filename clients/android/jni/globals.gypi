{
  'target_defaults': {
    'defines': [
      # Fix for thread free-before-use bug in clang++ 3.3 (for ARM targets. it
      # was fixed before for x86)
      '__GCC_HAVE_SYNC_COMPARE_AND_SWAP_1',
      '__GCC_HAVE_SYNC_COMPARE_AND_SWAP_2',
      '__GCC_HAVE_SYNC_COMPARE_AND_SWAP_4',
      '__GCC_HAVE_SYNC_COMPARE_AND_SWAP_8',
    ],
    'cflags_cc': [
       '-std=c++11',
       '-stdlib=libc++',
       '-frtti',
       '-g',
    ],
  },
}
