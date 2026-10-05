import hashlib,json,re,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from current_apps_overlay import configure_board
from build_legacy_sleep import legacy_inputs
class MotionSources(unittest.TestCase):
 def test_verbatim_sensor_sources(self):
  root=ROOT/'vendor/SensorLib';record=json.loads((root/'PROVENANCE.json').read_text())
  self.assertEqual(record['commit'],'477fc682e9ed30ced39774f3b7e93a1504968884')
  for name,digest in record['files'].items():
   self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest,name)
   self.assertEqual(record['source_paths'][name],name if name=='LICENSE' else 'src/'+name)
  self.assertTrue((root/'NOTICE-BMA423.txt').read_text().startswith('/**'))
 def test_both_distinct_feature_images(self):
  values=[]
  for name in ('bma423','bma456h'):
   text=(ROOT/'vendor/SensorLib/bosch/bma4xx'/(name+'.c')).read_text()
   data=text.split('const uint8_t '+name+'_config_file[] = {',1)[1].split('};',1)[0]
   values.append(bytes(int(x,16) for x in re.findall(r'0x([0-9a-fA-F]{2})',data)))
  self.assertEqual([len(x) for x in values],[6144,6144]);self.assertNotEqual(*values)
 def test_only_motion_polarity_changes_in_eight_physical_profiles(self):
  old=legacy_inputs(ROOT)
  for p in (ROOT/'hardware').glob('*.json'):
   expected=json.loads((old/'hardware'/p.name).read_text());motion=next(d for d in expected['devices'] if d['instance_id']==7)
   motion['config']['irq_active_high']=True;motion['config']['irq_pull_up']=False
   self.assertEqual(json.loads(p.read_text()),expected,p.name)
 def test_explicit_chip_model_and_no_replacement(self):
  for name,chip in [('bma423',0x13),('bma456h',0x16)]:
   board=configure_board({'devices':[],'buses':[]},ROOT,motion_model=name,radio_model='sx1262-915');motion=next(d for d in board['devices'] if d['instance_id']==7)
   self.assertEqual(motion['chip']['model'],name);self.assertEqual(motion['config']['chip_id'],chip)
   self.assertTrue(motion['config']['irq_active_high']);self.assertFalse(motion['config']['irq_pull_up'])
  for name in (None,'bma456','automatic','unknown'):
   with self.assertRaises(ValueError):configure_board({'devices':[],'buses':[]},ROOT,motion_model=name,radio_model='sx1262-915')
  with self.assertRaises(ValueError):configure_board({'devices':[{'instance_id':7}]},ROOT,motion_model='bma423',radio_model='sx1262-915')
