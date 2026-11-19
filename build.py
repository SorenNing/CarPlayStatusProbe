import io,os,tarfile,copy,gzip,hashlib,json,plistlib,subprocess,struct,math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.chdir(ROOT)
OUT=ROOT/'dist';OUT.mkdir(exist_ok=True)
SHA='b0004cd4fda700e66d5f9ea7f454576c1a3da40fe08df900987efce8ee86dde6'
def sha(b):return hashlib.sha256(b).hexdigest()
def run(*a,check=True):
 p=subprocess.run(a,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 with (OUT/'build.log').open('a') as f:f.write('$ '+' '.join(a)+'\n'+p.stdout+'\n')
 if check and p.returncode:raise RuntimeError('Command failed: '+' '.join(a)+'\n'+p.stdout)
 return {'command':list(a),'returncode':p.returncode,'output':p.stdout}
def arread(b):
 assert b[:8]==b'!<arch>\n';out={};pos=8
 while pos<len(b):
  h=b[pos:pos+60];assert h[58:60]==b'`\n';n=int(h[48:58]);out[h[:16].decode().strip().rstrip('/')]=b[pos+60:pos+60+n];pos+=60+n+n%2
 assert pos==len(b);return out
def unpack(b):
 with tarfile.open(fileobj=io.BytesIO(b),mode='r:*') as t:return [(copy.copy(m),t.extractfile(m).read() if m.isfile() else None) for m in t]
def tar(entries):
 b=io.BytesIO()
 with tarfile.open(fileobj=b,mode='w',format=tarfile.GNU_FORMAT) as t:
  for m,d in entries:
   m=copy.copy(m);m.mtime=0
   if d is not None:m.size=len(d)
   t.addfile(m,io.BytesIO(d) if d is not None else None)
 return gzip.compress(b.getvalue(),mtime=0)
def mkdeb(control,data):
 b=bytearray(b'!<arch>\n')
 for n,d in [('debian-binary',b'2.0\n'),('control.tar.gz',tar(control)),('data.tar.gz',tar(data))]:
  b.extend(f'{n+"/":<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(d):<10}`\n'.encode());b.extend(d)
  if len(d)%2:b.extend(b'\n')
 return bytes(b)
def add(name,b,mode=0o644):
 m=tarfile.TarInfo('./'+name);m.uid=m.gid=0;m.uname=m.gname='root';m.mode=mode;return (m,b)
def slices(b):
 if b[:4]==b'\xca\xfe\xba\xbe':
  count=struct.unpack_from('>I',b,4)[0];return [dict(zip(['cpu','subtype','offset','size','align'],struct.unpack_from('>IIIII',b,8+20*i))) for i in range(count)]
 magic,cpu,subtype=struct.unpack_from('<III',b);assert magic==0xfeedfacf
 return [{'cpu':cpu,'subtype':subtype,'offset':0,'size':len(b)}]
source=(ROOT/'vendor/statusbar-1.2-1.deb').read_bytes();assert sha(source)==SHA
parts=arread(source);data=unpack(next(v for k,v in parts.items() if k.startswith('data.tar')));control=unpack(next(v for k,v in parts.items() if k.startswith('control.tar')))
lookup={m.name.lstrip('./'):d for m,d in data if m.isfile()}
original=lookup['Library/MobileSubstrate/DynamicLibraries/iOS27StatusBar.dylib'];assert sha(original)=='709baf93799bf42d9adb5efcc389e290f538aaf8c6d697a386d58481c8c83a77'
original_path=OUT/'original-iOS27StatusBar.dylib';original_path.write_bytes(original)
verification={'source_sha256':SHA,'original_dylib_sha256':sha(original),'original_slices':slices(original),'original_signature':run('codesign','--verify','--strict','--all-architectures','--verbose=4',str(original_path),check=False),'original_dependencies':run('xcrun','otool','-arch','all','-L',str(original_path)),'environment':run('xcodebuild','-version'),'sdk':run('xcrun','--sdk','iphoneos','--show-sdk-version'),'probes':{},'packages':[],'runtime_tested':False,'installed':False,'rootless_deb':{'produced':False,'reason':'Original binary depends on @loader_path/.jbroot/usr/lib/libsubstrate.dylib. Moving Library to var/jb would not adapt this dependency; altering the original binary conflicts with byte preservation.'}}
sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
for arch,subtype in [('arm64',0),('arm64e',0x80000002)]:
 path=OUT/('CarPlayStatusProbe-'+arch+'.dylib')
 run('xcrun','--sdk','iphoneos','clang','-arch',arch,'-isysroot',sdk,'-miphoneos-version-min=14.0','-dynamiclib','-fobjc-arc','-fblocks','-O2','-Wall','-Wextra','-framework','UIKit','-framework','Foundation','-Wl,-install_name,@rpath/CarPlayStatusProbe.dylib','src/CarPlayStatusProbe.m','-o',str(path))
 run('codesign','--force','--sign','-','--timestamp=none',str(path))
 sig=run('codesign','--verify','--strict','--all-architectures','--verbose=4',str(path));b=path.read_bytes();s=slices(b);assert len(s)==1 and s[0]['cpu']==0x100000c and s[0]['subtype']==subtype,s
 verification['probes'][arch]={'sha256':sha(b),'size':len(b),'slices':s,'signature':sig,'dependencies':run('xcrun','otool','-L',str(path))}
newdata=[]
for m,d in data:
 n=m.name.lstrip('./')
 if n=='Library/MobileSubstrate/DynamicLibraries/iOS27StatusBar.plist':
  p=plistlib.loads(d);assert p=={'Filter':{'Bundles':['com.apple.springboard']}};p['Filter']['Bundles'].append('com.apple.CarPlayApp');d=plistlib.dumps(p,sort_keys=False)
 newdata.append((m,d))
prefix='Library/MobileSubstrate/DynamicLibraries/'
newdata += [add(prefix+'CarPlayStatusProbe.dylib',(OUT/'CarPlayStatusProbe-arm64e.dylib').read_bytes(),0o755),add(prefix+'CarPlayStatusProbe.plist',plistlib.dumps({'Filter':{'Bundles':['com.apple.CarPlayApp']}}))]
files={m.name.lstrip('./'):d for m,d in newdata if m.isfile()}
installed=sum(math.ceil(len(d)/1024) for d in files.values())
newcontrol=[]
for m,d in control:
 n=m.name.lstrip('./')
 if n=='md5sums':continue
 if n=='control':
  text=d.decode();assert 'Architecture: iphoneos-arm64e\n' in text and 'Depends: mobilesubstrate\n' in text
  text=text.replace('Version: 1.2-1\n','Version: 1.2-1+carplaydiag1\n')
  for k in ['Maintainer','Author']:text=text.replace(k+': 半生年华&yaowell&Benja Guo',k+': Ning&半生年华&yaowell&Benja Guo')
  text='\n'.join('Installed-Size: '+str(installed) if l.startswith('Installed-Size:') else l for l in text.splitlines())+'\n';d=text.encode()
 newcontrol.append((m,d))
newcontrol.append(add('md5sums',''.join(hashlib.md5(d).hexdigest()+'  '+n+'\n' for n,d in sorted(files.items())).encode()))
package=mkdeb(newcontrol,newdata);filename='iOS27StatusBar-1.2-1+carplaydiag1-iphoneos-arm64e.deb';(OUT/filename).write_bytes(package)
# Verify the serialized final package, not only the in-memory inputs.
p=arread(package);actual=unpack(p['data.tar.gz']);got={m.name.lstrip('./'):d for m,d in actual if m.isfile()};ctl={m.name.lstrip('./'):d for m,d in unpack(p['control.tar.gz']) if m.isfile()}
assert got==files
assert sha(got[prefix+'iOS27StatusBar.dylib'])==sha(original)
for n,d in lookup.items():
 if n!=prefix+'iOS27StatusBar.plist':assert got[n]==d,n
assert all(not m.name.lstrip('./').startswith('var/jb/') for m,d in actual)
for line in ctl['md5sums'].decode().splitlines():
 digest,n=line.split(None,1);assert hashlib.md5(got[n]).hexdigest()==digest
assert plistlib.loads(got[prefix+'CarPlayStatusProbe.plist'])=={'Filter':{'Bundles':['com.apple.CarPlayApp']}}
assert slices(got[prefix+'CarPlayStatusProbe.dylib'])[0]['subtype']==0x80000002
verification['packages'].append({'file':filename,'size':len(package),'sha256':sha(package),'architecture':'iphoneos-arm64e','version':'1.2-1+carplaydiag1','installed_size_kib':installed,'md5sums_verified':True,'original_payload_preserved_except_filter':True,'original_dylib_byte_identical':True,'layout':'original RootHide root Library layout; no new conversion','depends':'mobilesubstrate','files':[{'path':m.name,'mode':oct(m.mode),'size':m.size} for m,d in actual]})
(OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'packages':verification['packages'],'probes':{k:{'sha256':v['sha256'],'slices':v['slices']} for k,v in verification['probes'].items()}},indent=2))
