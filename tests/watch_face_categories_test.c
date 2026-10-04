#include "apps/clock/faces/picker.h"
#include <assert.h>
#include <stdio.h>
static watch_face_picker opened(unsigned id){watch_face_picker p={.selected=(uint8_t)id};watch_face_input(&p,0,true,0,0,0,0);watch_face_input(&p,1,true,1,1,120,120);assert(watch_face_input(&p,601,true,1,1,120,120)==WATCH_FACE_OPEN);watch_face_input(&p,602,true,0,0,0,0);return p;}
static void settle(watch_face_picker*p,unsigned now){for(unsigned t=now;t<=now+5000;t+=20)watch_face_animate(p,t);assert(watch_category_settled(p));}
static void down(watch_face_picker*p,unsigned now,int y){assert(!watch_face_input(p,now,true,1,1,120,(unsigned)y));}
static void up(watch_face_picker*p,unsigned now){assert(!watch_face_input(p,now,true,0,0,0,0));}
int main(void){
 unsigned seen[WATCH_FACE_COUNT]={0};for(unsigned c=0;c<4;c++){const watch_face_page*q=watch_face_page_for(c);for(unsigned i=0;i<q->count;i++){seen[q->ids[i]]++;assert(watch_face_category_for(q->ids[i])==c&&watch_face_index_for(c,q->ids[i])==i);}}
 for(unsigned i=0;i<24;i++)assert(seen[i]==1);
 watch_face_picker p=opened(0);assert(p.category==1&&p.position==0&&p.category_position==-WATCH_CATEGORY_PITCH);
 down(&p,700,200);down(&p,800,140);assert(p.axis==2&&p.category_position==-WATCH_CATEGORY_PITCH-60*256&&p.category==1);
 down(&p,900,40);assert(p.category_position==-WATCH_CATEGORY_PITCH-160*256&&p.category==2&&p.selected==0);
 up(&p,1100);settle(&p,1100);assert(p.category==2);
 /* A slow half-drag reverses with the finger, then settles back without a jump. */
 down(&p,7000,120);down(&p,7100,40);int half=p.category_position;down(&p,7200,100);assert(p.category_position==half+60*256);up(&p,7400);settle(&p,7400);assert(p.category==2);
 /* Cancelled/invalid contacts settle to the nearest row and cannot select. */
 down(&p,13000,210);down(&p,13100,40);int displaced=p.category_position;
 assert(!watch_face_input(&p,13101,false,0,0,0,0)&&p.category_position==displaced);
 down(&p,13102,120);assert(!p.down);up(&p,13200);settle(&p,13200);assert(p.category==3);
 /* Both seams wrap continuously and support reversal before release. */
 p=opened(16);down(&p,700,210);down(&p,800,40);assert(p.category==0&&p.category_position==-890*256);up(&p,1000);settle(&p,1000);assert(p.category==0&&p.category_position==0);
 p=opened(1);down(&p,700,40);down(&p,800,210);assert(p.category==3&&p.category_position==-790*256);down(&p,820,100);assert(p.category==0&&p.category_position==-900*256);down(&p,840,40);assert(p.category_position==0);up(&p,1000);settle(&p,1000);assert(p.category==0);
 p=opened(1);down(&p,700,40);down(&p,800,210);up(&p,1000);settle(&p,1000);assert(p.category==3&&p.category_position==-720*256);
 /* One locked axis; horizontal motion cannot move a collection. */
 p=opened(0);down(&p,700,120);watch_face_input(&p,720,true,1,1,108,119);assert(p.axis==1);watch_face_input(&p,740,true,1,1,40,40);up(&p,760);assert(p.category_position==-WATCH_CATEGORY_PITCH&&p.position<0);
 p=opened(0);down(&p,700,120);down(&p,720,108);int x=p.position;watch_face_input(&p,740,true,1,1,40,106);assert(p.axis==2&&p.position==x);up(&p,900);settle(&p,900);assert(p.category==1);
 /* A tap catches a moving collection but cannot save an uncentered face. */
 p=opened(0);down(&p,700,210);down(&p,800,40);up(&p,1000);down(&p,1001,92);assert(p.tap_blocked);up(&p,1010);settle(&p,1010);down(&p,7000,92);assert(watch_face_input(&p,7010,true,0,0,0,0)==WATCH_FACE_SELECT);assert(watch_face_page_for(p.category)->ids[p.target]==2);
 /* Exact trajectories at arbitrary presentation intervals, including edges. */
 const unsigned intervals[]={1,8,20,50,95};
 for(unsigned boundary=0;boundary<3;boundary++) {
  watch_face_picker seed=opened(0);seed.last_tick=0;seed.category_position=boundary==0?-300*256:boundary==1?24*256:-744*256;seed.category_velocity=boundary==1?6*256:-6*256;seed.category_snapping=false;
  watch_face_picker expected=seed;for(unsigned t=1;t<=5000;t++)watch_face_animate(&expected,t);
  for(unsigned n=0;n<5;n++){watch_face_picker q=seed;unsigned t=0;while(t<5000){t+=intervals[n];if(t>5000)t=5000;watch_face_animate(&q,t);}assert(q.category_position==expected.category_position&&q.category_velocity==expected.category_velocity&&q.category==expected.category&&q.phase==expected.phase);assert(watch_category_settled(&q));}
 }
 /* Pointer sampling cadence still follows the same distance; velocity is in
  * px/60Hz rather than pixels per event. A held release removes fling noise. */
 for(unsigned step=8;step<=40;step+=8){p=opened(0);down(&p,700,200);for(unsigned t=step;t<320;t+=step)down(&p,700+t,200-(int)t/2);down(&p,1020,40);assert(p.category_position==-400*256);up(&p,1200);settle(&p,1200);assert(p.category==2);}
 for(unsigned id=0;id<24;id++){p=opened(id);assert(watch_face_page_for(p.category)->ids[p.target]==id&&p.position==-(int)p.target*WATCH_FACE_PITCH&&watch_category_settled(&p));watch_face_close(&p);assert(!p.open&&!p.down);}
 puts("24 stable IDs; continuous vertical drag/reversal, axis lock, cancelled contacts, cyclic seams/reversal, transition tap safety and 1/8/20/50/95ms deterministic settling passed");
}
