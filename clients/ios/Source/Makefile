# Support for emacs flymake, for on-the-fly syntax checking.
#
# To enable this, add the following to your .emacs:
# (load "flymake")
# ; without this flymake pops up a dialog if if can't start up
# (setq flymake-gui-warnings-enabled nil)
# (add-to-list 'flymake-allowed-file-name-masks
#              '("\\.mm\\'" flymake-simple-make-init))
# (add-to-list 'flymake-allowed-file-name-masks
#              '("\\.h\\'" flymake-simple-make-init))
# (add-hook 'find-file-hook
#           (lambda ()
#             (if (string-match "clients/ios/Source/.*\\(\\.mm\\|\\.h\\)$"
#                               buffer-file-name)
#                 (flymake-mode 1))))


# It would be great if we could extract this from xcode/gyp somehow.  This is
# cobbled together from information on the web.
CLANG	    = clang
ARCH	    = -arch i386
SDK	    = -isysroot /Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator7.0.sdk
OS_VER_MIN  = -mios-simulator-version-min=6.0
OPTIONS     = -fobjc-arc -fobjc-abi-version=2 -x objective-c++ -DTESTING=1 -DFLYMAKE=1 -DDEVELOPMENT=1 -std=c++11 -stdlib=libc++
# Note that in clang -Wall is not everything.  There is a second tier of
# options enabled with -Wextra, and -Weverything is every possible warning.
# http://programmers.stackexchange.com/questions/122608/clang-warning-flags-for-objective-c-development
WARNINGS    = -Wall
# Some of our third-party libraries (gdata) have weird include setups
# that I'm not sure how to handle.
INCLUDES    = -I. -I.. -I../../shared -ITests -I../third_party -I../third_party/facebook/ -I../third_party/mongoose -I ../third_party_shared/re2 -I ../third_party/phonenumbers/cpp/src -I ../third_party/plcrashreporter/Source -I ../third_party/icu/source/i18n -I ../third_party/icu/source/common -I../third_party_shared/protobuf/src -I../third_party_shared/leveldb/include -I$(shell echo ${HOME}/Library/Developer/Xcode/DerivedData/ViewfinderWorkspace-*/Build/Products/DerivedSources/Debug)
FRAMEWORKS  = -F../third_party

# The || true is necessary in case clang reports no problems with the .mm file,
# but there are errors in a .h (flymake gets confused if check-syntax fails
# but reports no errors in the file it cares about)
check-syntax:
	$(CLANG) -fsyntax-only $(OPTIONS) $(ARCH) $(WARNINGS) $(SDK) $(OS_VER_MIN) $(INCLUDES) $(FRAMEWORKS) ${CHK_SOURCES} || true
