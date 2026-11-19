#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <dlfcn.h>

// Read-only UIKit observer. No swizzling, image replacement, or private writes.
static NSMutableArray *gSnapshots;
static NSString *gLogPath;
static unsigned gRound;
static void CPProbeSnapshot(void);

static id CPReadScalar(id object, NSString *name) {
    SEL sel = NSSelectorFromString(name);
    if (![object respondsToSelector:sel]) return @"unavailable";
    NSMethodSignature *sig = [object methodSignatureForSelector:sel];
    if (!sig || sig.numberOfArguments != 2) return @"unsupported-signature";
    const char *t = sig.methodReturnType;
    NSInvocation *inv = [NSInvocation invocationWithMethodSignature:sig];
    inv.target = object; inv.selector = sel;
    @try {
        [inv invoke];
        if (!strcmp(t,"B")) { BOOL v=NO; [inv getReturnValue:&v]; return @(v); }
        if (!strcmp(t,"c")) { signed char v=0; [inv getReturnValue:&v]; return @(v); }
        if (!strcmp(t,"q")) { long long v=0; [inv getReturnValue:&v]; return @(v); }
        if (!strcmp(t,"Q")) { unsigned long long v=0; [inv getReturnValue:&v]; return @(v); }
        if (!strcmp(t,"i")) { int v=0; [inv getReturnValue:&v]; return @(v); }
        if (!strcmp(t,"f")) { float v=0; [inv getReturnValue:&v]; return @(v); }
        if (!strcmp(t,"d")) { double v=0; [inv getReturnValue:&v]; return @(v); }
        return @"unsupported-return";
    } @catch (NSException *e) { return e.name ?: @"exception"; }
}

static NSDictionary *CPMethod(Class cls, NSString *name) {
    Method method = class_getInstanceMethod(cls, NSSelectorFromString(name));
    if (!method) return @{@"present":@NO};
    const char *encoding = method_getTypeEncoding(method);
    IMP imp = method_getImplementation(method);
    Dl_info info = {0};
    dladdr((const void *)imp, &info);
    NSString *image = info.dli_fname ? [[NSString stringWithUTF8String:info.dli_fname] lastPathComponent] : @"unknown";
    return @{@"present":@YES, @"encoding":encoding ? @(encoding) : @"", @"image":image};
}

static void CPWalk(UIView *view, NSString *path, unsigned depth, NSMutableArray *rows, unsigned *visited) {
    if (depth > 24 || ++(*visited) > 12000 || rows.count >= 600) return;
    NSString *name = NSStringFromClass(view.class);
    NSString *next = [path stringByAppendingFormat:@"/%@",name];
    BOOL relevant = NO;
    for (NSString *s in @[@"Battery", @"Wifi", @"WiFi", @"Signal", @"StatusBar"]) {
        if ([name containsString:s]) { relevant=YES; break; }
    }
    if (relevant) {
        NSMutableDictionary *row = [@{@"class":name,@"path":next,@"bounds":NSStringFromCGRect(view.bounds),@"hidden":@(view.hidden),@"alpha":@(view.alpha)} mutableCopy];
        for (NSString *s in @[@"showsPercentage",@"_currentlyShowsPercentage",@"chargePercent",@"chargingState",@"numberOfActiveBars",@"numberOfBars",@"signalMode",@"iconSize"]) row[s]=CPReadScalar(view,s);
        NSMutableDictionary *methods=[NSMutableDictionary dictionary];
        for (NSString *s in @[@"layoutSubviews",@"_updateActiveBars",@"setNumberOfActiveBars:",@"setShowsPercentage:",@"_updateBolt",@"_updateLightningBoltAndPercentagePosition",@"_batteryTextColor"]) methods[s]=CPMethod(view.class,s);
        row[@"methods"]=methods;
        [rows addObject:row];
    }
    for (UIView *child in [view.subviews copy]) CPWalk(child,next,depth+1,rows,visited);
}

static void CPProbeSnapshot(void) {
    @autoreleasepool {
        NSMutableSet *windows=[NSMutableSet setWithArray:UIApplication.sharedApplication.windows];
        for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
            if ([scene isKindOfClass:UIWindowScene.class]) [windows addObjectsFromArray:((UIWindowScene *)scene).windows];
        }
        NSMutableArray *rows=[NSMutableArray array];
        unsigned visited=0;
        for (UIWindow *window in windows) CPWalk(window,@"",0,rows,&visited);
        NSMutableDictionary *classes=[NSMutableDictionary dictionary];
        for (NSString *n in @[@"_UIBatteryView",@"_UIStatusBarBatteryView",@"_UIStatusBarStaticBatteryView",@"_UIStatusBarWifiSignalView"]) {
            Class c=NSClassFromString(n);
            NSMutableDictionary *entry=[@{@"present":@(c!=Nil)} mutableCopy];
            if(c) for(NSString *s in @[@"setShowsPercentage:",@"_updateBolt",@"_updateLightningBoltAndPercentagePosition",@"_batteryTextColor"]) entry[s]=CPMethod(c,s);
            classes[n]=entry;
        }
        [gSnapshots addObject:@{@"round":@(gRound++),@"time":@(NSDate.date.timeIntervalSince1970),@"windowCount":@(windows.count),@"visited":@(visited),@"classes":classes,@"views":rows}];
        NSDictionary *report=@{@"probeVersion":@1,@"bundle":NSBundle.mainBundle.bundleIdentifier ?: @"",@"systemVersion":UIDevice.currentDevice.systemVersion,@"snapshots":gSnapshots};
        NSError *error=nil;
        NSData *data=[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:&error];
        if(data && ![data writeToFile:gLogPath options:NSDataWritingAtomic error:&error]) NSLog(@"[CarPlayStatusProbe] write failed %@",error);
    }
}

__attribute__((constructor)) static void CPProbeLoad(void) {
    @autoreleasepool {
        if (![NSBundle.mainBundle.bundleIdentifier isEqualToString:@"com.apple.CarPlayApp"]) return;
        gSnapshots=[NSMutableArray array];
        gLogPath=[NSTemporaryDirectory() stringByAppendingPathComponent:@"CarPlayStatusProbe.json"];
        NSLog(@"[CarPlayStatusProbe] output %@",gLogPath);
        // Finite sampling: catches initial views and later connected display setup.
        for (NSNumber *seconds in @[@1,@3,@8,@15,@30,@60]) {
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW,(int64_t)(seconds.doubleValue*NSEC_PER_SEC)),dispatch_get_main_queue(),^{ CPProbeSnapshot(); });
        }
    }
}
