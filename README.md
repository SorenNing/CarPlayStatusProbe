# CarPlayStatusProbe

作者：Ning&半生年华&yaowell&Benja Guo。

原生只读诊断测试工程。用户已实测此前仅扩展过滤器的 carplay1 版本只有信号生效；本版本采集电池/Wi-Fi视图和方法信息，不声称修复或真机验证。

## Sources and reproducibility

`src/CarPlayStatusProbe.m` is the complete source of our new observer, copied unchanged from the reviewed native-observer source. It does not install hooks or write private UIKit state. Its constructor gates on `com.apple.CarPlayApp`; the observer records snapshots on the main queue after 1/3/8/15/30/60 seconds. Output: `NSTemporaryDirectory()/CarPlayStatusProbe.json` in the CarPlay process. It starts only after the process next loads the installed tweak. No Frida or manual script loading is needed.

`vendor/statusbar-1.2-1.deb` is a third-party precompiled package, NOT source code. Its SHA-256 is `b0004cd4fda700e66d5f9ea7f454576c1a3da40fe08df900987efce8ee86dde6`. Original iOS27StatusBar.dylib SHA-256 is `709baf93799bf42d9adb5efcc389e290f538aaf8c6d697a386d58481c8c83a77`. Original visual logic, fat arm64/arm64e binary bytes and existing signature are preserved. Only its bundle filter gains `com.apple.CarPlayApp`. New observer filter contains only `com.apple.CarPlayApp`.

Run `python3 build.py` on macOS with Xcode/iPhoneOS SDK. This invokes xcrun clang separately for real arm64 and arm64e, uses Foundation/UIKit, ad-hoc signs both new dylibs and verifies with codesign strict/all-architectures. arm64e must have Mach-O CPU subtype 0x80000002. Python creates Debian ar/tar archives (no macOS ar), updates Installed-Size and generates/checks md5sums. Final serialized package is re-read and checked. Build outputs include both independent diagnostic dylibs, the RootHide deb, verification.json and build.log.

## Package compatibility

Version: 1.2-1+carplaydiag1. Original Architecture iphoneos-arm64e, Depends mobilesubstrate and root Library layout are retained. This is an original-layout RootHide package, not a newly converted RootHide package.

A normal arm64 rootless deb is intentionally withheld: original binary LC_LOAD_DYLIB depends on `@loader_path/.jbroot/usr/lib/libsubstrate.dylib` in BOTH slices, with matching RootHide-style install ID. Merely moving Library to var/jb and changing Architecture does not adapt it. Rewriting load commands and resigning would change original dylib bytes, which this build must preserve. The independently compiled arm64 observer is supplied for evidence, not as an installable normal rootless package.

The preferences bundle's executable in the original package is zero bytes; this build preserves it rather than inventing a repair. Original signature verification result is recorded without resigning or changing it.

The workflow has only workflow_dispatch, so pushing source does not trigger builds. Single authorized dispatch; do not rerun automatically on failure. No installation, injection, process restart or package-repository publication is performed.
