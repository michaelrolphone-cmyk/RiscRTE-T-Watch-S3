import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from shared_optional_hardware import provision, OPTIONAL

class OptionalHardware(unittest.TestCase):
    def test_present_absent_preserve_other_authority(self):
        for app, caps in OPTIONAL.items():
            rows=[{'capability':c,'api':2 if c in ('rtc.clock','radio.lora') else 1}
                  for c in ['display.output','input.touch.raw',*sorted(caps)]]
            m={'id':app,'file_name':app+'.elf','requires':rows}
            p={'manifest':app+'.json','grants':[dict(r,instance_id=0) for r in rows]}
            original=copy.deepcopy((m,p))
            for absent in ((),caps):
                new,policy=provision(m,p,absent)
                self.assertEqual(new['requires'],rows[:2])
                self.assertEqual(new['optional'],rows[2:])
                self.assertEqual(policy['grants'],[g for g in p['grants'] if g['capability'] not in absent])
                self.assertEqual(provision(new,policy,absent),(new,policy))
            self.assertEqual((m,p),original)
            with self.assertRaises(ValueError):provision(m,p,['display.output'])

if __name__=='__main__':unittest.main()
