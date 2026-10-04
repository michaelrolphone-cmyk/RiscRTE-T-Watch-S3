#include "apps/clock/faces/picker.h"
#include <assert.h>
#include <stdio.h>
static void swipe(watch_face_picker*p,int dx,int dy,unsigned now){watch_face_input(p,now,true,0,0,0,0);watch_face_input(p,now+1,true,1,1,120,120);watch_face_input(p,now+9,true,1,1,120+dx,120+dy);watch_face_input(p,now+17,true,0,0,0,0);}
int main(void){
 unsigned seen[WATCH_FACE_COUNT]={0};for(unsigned c=0;c<4;c++){const watch_face_page*q=watch_face_page_for(c);for(unsigned i=0;i<q->count;i++){seen[q->ids[i]]++;assert(watch_face_category_for(q->ids[i])==c&&watch_face_index_for(c,q->ids[i])==i);}}
 for(unsigned i=0;i<24;i++)assert(seen[i]==1);
 watch_face_picker p={0};watch_face_input(&p,0,true,0,0,0,0);watch_face_input(&p,1,true,1,1,120,120);assert(watch_face_input(&p,601,true,1,1,120,120)==WATCH_FACE_OPEN);assert(p.category==1&&p.position==0);
 swipe(&p,2,-60,700);assert(p.category==2&&p.position==0&&p.selected==0);
 swipe(&p,3,-60,800);assert(p.category==3&&p.position==0);
 swipe(&p,0,-60,900);assert(p.category==3);
 swipe(&p,1,60,1000);assert(p.category==2);
 int pos=p.position;swipe(&p,-60,2,1100);assert(p.category==2&&p.position<pos);
 /* Direction is chosen once, even if the finger later crosses the other axis. */
 watch_face_input(&p,1200,true,0,0,0,0);watch_face_input(&p,1201,true,1,1,120,120);watch_face_input(&p,1209,true,1,1,108,119);assert(p.axis==1);watch_face_input(&p,1217,true,1,1,106,40);watch_face_input(&p,1225,true,0,0,0,0);assert(p.category==2);
 watch_face_input(&p,1300,true,1,1,120,120);watch_face_input(&p,1308,true,1,1,119,108);assert(p.axis==2);int held=p.position;watch_face_input(&p,1316,true,1,1,40,106);assert(p.position==held);watch_face_input(&p,1324,true,0,0,0,0);assert(p.category==2); /* <24px vertical = cancel */
 /* Every persisted global identity reopens in its actual category and slot. */
 for(unsigned id=0;id<24;id++){p=(watch_face_picker){.selected=(uint8_t)id};watch_face_input(&p,0,true,0,0,0,0);watch_face_input(&p,1,true,1,1,120,120);assert(watch_face_input(&p,601,true,1,1,120,120)==WATCH_FACE_OPEN);assert(watch_face_page_for(p.category)->ids[p.target]==id&&p.position==-(int)p.target*WATCH_FACE_PITCH);}
 puts("24 stable IDs exactly once; vertical categories, horizontal cards, axis lock/cancellation, bounds and selected-page restoration passed");
}
