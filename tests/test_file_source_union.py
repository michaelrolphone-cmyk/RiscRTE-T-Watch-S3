import copy,json,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import bind_watch_file_source as b
import assemble_watch_file_source as a
class UnionTest(unittest.TestCase):
 def setUp(self):
  rows=[{'manifest':n+'.json','grants':[{'capability':'original','api':1,'instance_id':9}]} for n in ('file_browser','model_viewer','ble_scanner','settings','other')]
  self.old={'boot.json':b.encoded({'drivers':[{'manifest':'text-input/manifest.json'}],'app_capabilities':rows}),'other.elf':b'original'}
  for n in ('file_browser','model_viewer','ble_scanner','settings'):
   self.old[n+'.json']=b.encoded({'id':n,'version':'old','requires':[{'capability':'original','api':1}]});self.old[n+'.elf']=b'old'
  self.old['alarm-service/manifest.json']=b.encoded({'id':'alarm','version':'old','requires':[]});self.old['alarm-service/driver.elf']=b'old'
  source=[]
  for n,v in [('file_browser','1.5.33'),('model_viewer','1.3.1')]:
   j=json.loads(self.old[n+'.json']);j['version']=v;j['requires'].append(b.REQUIREMENT);source.append(b.encoded(j))
  full=b.changed_store(self.old,b'new-files',source[0],b'new-viewer',source[1]);self.overlay={n:full[n] for n in b.CHANGED}
  self.rtc={n:b'new' for n in a.RTC_MEMBERS}
  for n,v in [('settings.json','1.3.24'),('alarm-service/manifest.json','0.4.9')]:j=json.loads(self.old[n]);j['version']=v;self.rtc[n]=b.encoded(j)
  j=json.loads(self.old['ble_scanner.json']);j['version']='0.2.18';j['requires'].append({'capability':'ui.text-input','api':1});self.scanner={'ble_scanner.json':b.encoded(j),'ble_scanner.elf':b'new-scanner'}
 def test_three_additive_grants(self):
  new=a.source_union(self.old,self.overlay,self.scanner,self.rtc);before=json.loads(self.old['boot.json']);after=json.loads(new['boot.json']);self.assertEqual(before['drivers'],after['drivers']);self.assertEqual(new['other.elf'],b'original')
  for i in range(5):self.assertEqual(after['app_capabilities'][i]['grants'][:1],before['app_capabilities'][i]['grants']);self.assertEqual(len(after['app_capabilities'][i]['grants']),2 if i<3 else 1)
 def test_source_overlay_cannot_overwrite_scanner(self):
  boot=json.loads(self.overlay['boot.json']);boot['app_capabilities'][2]['grants']=[];self.overlay['boot.json']=b.encoded(boot)
  with self.assertRaisesRegex(ValueError,'unrelated authority'):a.source_union(self.old,self.overlay,self.scanner,self.rtc)
 def test_rtc_cannot_change_authority(self):
  j=json.loads(self.rtc['settings.json']);j['requires']=[];self.rtc['settings.json']=b.encoded(j)
  with self.assertRaisesRegex(ValueError,'RTC manifest'):a.source_union(self.old,self.overlay,self.scanner,self.rtc)
if __name__=='__main__':unittest.main()
