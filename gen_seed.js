const fs = require('fs');
const path = require('path');
const OUT = path.join(__dirname, 'seed');
fs.rmSync(OUT, {recursive: true, force: true});
fs.mkdirSync(OUT, {recursive: true});

// deterministic pseudo-random so reruns are stable
let s = 20260912;
function rnd() { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; }
function pick(a) { return a[Math.floor(rnd() * a.length)]; }
function iRange(lo, hi) { return lo + Math.floor(rnd() * (hi - lo + 1)); }

const FIRST = ['Amara','Diego','Priya','Noah','Leila','Malik','Sofia','Ethan','Yuki','Isabel','Omar','Hannah','Tobias','Nadia','Caleb','Mei','Rafael','Grace','Jonas','Aaliyah','Simon','Elena','Kofi','Tessa','Dmitri','Rosa','Levi','Anjali','Marcus','Clara','Hassan','Ingrid','Theo','Naomi','Andre','Fatima','Quinn','Luca','Bea','Samir','Nora','Emeka','Iris','Jaden','Mira','Owen','Zara','Felix','Lucia','Arjun','Greta','Mateo','Ada','Kenji','Rosalind','Dario','Imani','Soren','Talia','Wren'];
const LAST = ['Osei','Ramirez','Nair','Bergstrom','Haddad','Johnson','Vargas','Whitfield','Tanaka','Moreau','Khalid','Lindqvist','Ferraro','Abiodun','Stone','Chen','Duarte','Okafor','Petrov','Washington','Hollis','Castellanos','Mensah','Vandermeer','Sokolov','Ibarra','Frankel','Deshmukh','Boone','Lindgren','Rahimi','Solberg','Marchetti','Adeyemi','Beaulieu','Zidane','Ellery','Rossi','Larkin','Habib','Kowalski','Nwosu','Ashford','Reyes','Sandoval','Gallagher','Bahri','Novak','Mendes','Pillai','Halvorsen','Quintero','Lovelace','Watanabe','Ashby','Bianchi','Cole','Aaltonen','Barnard','Fielding'];

const students = [];
for (let i = 0; i < 60; i++) {
  students.push({
    sid: 'S-1' + String(101 + i * 7).padStart(3, '0'),
    name: FIRST[i] + ' ' + LAST[i],
    grade: 6 + (i % 3),
    homeroom: ['6A','6B','7A','7B','8A','8B'][i % 6]
  });
}

// ---- courses -------------------------------------------------------------
const COURSES = [
  {code:'SCI-210', title:'Forensic Science',            dept:'Science',      teacher:'R. Okonkwo',   period:4, room:'S-214', capacity:24, enrolled:24, wait:19, isNew:true,  signups:[4,6,5,11,14,17,15,12], desc:'Evidence handling, fingerprint lifting, and chromatography labs built around a term-long case file.'},
  {code:'TEC-130', title:'Esports & Game Design',       dept:'Technology',   teacher:'J. Whitfield', period:7, room:'T-102', capacity:20, enrolled:20, wait:17, isNew:true,  signups:[2,5,9,12,13,16,14,13], desc:'Students build a playable level, then run a structured league with match analytics.'},
  {code:'CTE-118', title:'Intro to Robotics',           dept:'Career & Tech',teacher:'M. Delacroix', period:2, room:'T-108', capacity:18, enrolled:18, wait:14, isNew:true,  signups:[3,4,7,9,11,12,10,9],  desc:'Drivetrain assembly, sensor wiring, and an end-of-term table-top competition.'},
  {code:'PE-160',  title:'Rock Climbing',               dept:'Athletics',    teacher:'D. Boone',     period:6, room:'Gym Annex', capacity:16, enrolled:16, wait:9, isNew:true, signups:[2,3,6,8,9,10,8,7],  desc:'Top-rope technique and belay certification on the annex wall.'},
  {code:'ART-140', title:'Ceramics & Wheel Throwing',   dept:'Arts',         teacher:'L. Moreau',    period:3, room:'A-120', capacity:20, enrolled:20, wait:11, isNew:false, signups:[3,4,5,6,8,9,7,6],   desc:'Hand-building through glaze chemistry, finishing with a kiln-fired portfolio piece.'},
  {code:'ART-112', title:'Digital Photography',         dept:'Arts',         teacher:'L. Moreau',    period:5, room:'A-114', capacity:20, enrolled:19, wait:6,  isNew:true,  signups:[2,3,4,6,7,8,7,6],   desc:'Exposure fundamentals on loaner DSLRs, darkroom-free editing, and a print show.'},
  {code:'CTE-122', title:'Culinary Basics',             dept:'Career & Tech',teacher:'A. Ferraro',   period:5, room:'C-101', capacity:16, enrolled:15, wait:3,  isNew:false, signups:[2,2,3,4,4,5,4,4],   desc:'Knife skills, food-safety certification, and a family-night service.'},
  {code:'MAT-150', title:'Algebra Foundations',         dept:'Mathematics',  teacher:'S. Frankel',   period:1, room:'M-205', capacity:30, enrolled:28, wait:2,  isNew:false, signups:[6,5,4,4,3,3,2,2],   desc:'Linear reasoning and function notation; placement-tested entry.'},
  {code:'MAT-210', title:'Geometry',                    dept:'Mathematics',  teacher:'S. Frankel',   period:3, room:'M-207', capacity:30, enrolled:19, wait:0,  isNew:false, signups:[4,3,3,2,2,1,1,1],   desc:'Proof writing, transformations, and a scale-model capstone.'},
  {code:'SCI-118', title:'Life Science',                dept:'Science',      teacher:'R. Okonkwo',   period:2, room:'S-210', capacity:30, enrolled:27, wait:0,  isNew:false, signups:[5,4,4,3,3,2,2,2],   desc:'Cell structure through ecosystems, anchored by the courtyard pond study.'},
  {code:'ENG-201', title:'Creative Writing Workshop',   dept:'Humanities',   teacher:'T. Ellery',    period:6, room:'E-118', capacity:22, enrolled:17, wait:0,  isNew:false, signups:[4,3,3,3,2,2,2,1],   desc:'Weekly workshop cycle ending in a bound student anthology.'},
  {code:'WLD-101', title:'Spanish I',                   dept:'Humanities',   teacher:'C. Quintero',  period:1, room:'E-104', capacity:28, enrolled:25, wait:0,  isNew:false, signups:[5,4,4,3,3,2,2,2],   desc:'Present-tense conversation, with a spring exchange-letter project.'},
  {code:'MUS-105', title:'Jazz Band',                   dept:'Arts',         teacher:'P. Sandoval',  period:7, room:'A-101', capacity:28, enrolled:22, wait:0,  isNew:false, signups:[4,4,3,3,2,2,2,2],   desc:'Combo and big-band repertoire; audition or director approval.'},
  {code:'SOC-130', title:'Model UN',                    dept:'Humanities',   teacher:'T. Ellery',    period:4, room:'E-122', capacity:24, enrolled:11, wait:0,  isNew:false, signups:[3,2,2,1,1,1,0,1],   desc:'Position-paper research and two regional conference delegations.'}
];

function dayOffset(n) {
  const d = new Date(Date.UTC(2026, 7, 10));
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

// Build rosters: each student lands in several courses, no duplicates per course.
const load = new Map(students.map(s => [s.sid, 0]));
function nextStudents(count, taken) {
  const pool = students
    .filter(s => !taken.has(s.sid))
    .sort((a, b) => (load.get(a.sid) - load.get(b.sid)) || (a.sid < b.sid ? -1 : 1));
  return pool.slice(0, count);
}

const courseDocs = COURSES.map((c, ci) => {
  const taken = new Set();
  const roster = [];
  for (const st of nextStudents(c.enrolled, taken)) {
    taken.add(st.sid); load.set(st.sid, load.get(st.sid) + 1);
    roster.push({sid: st.sid, name: st.name, grade: st.grade, state: 'enrolled', at: dayOffset(iRange(0, 21))});
  }
  for (const st of nextStudents(c.wait, taken)) {
    taken.add(st.sid); load.set(st.sid, load.get(st.sid) + 1);
    roster.push({sid: st.sid, name: st.name, grade: st.grade, state: 'waitlist', at: dayOffset(iRange(22, 32))});
  }
  return {
    code: c.code, title: c.title, dept: c.dept, teacher: c.teacher,
    period: c.period, room: c.room, section: 'A', term: 'Fall 2026',
    capacity: c.capacity, status: 'open', isNew: c.isNew,
    description: c.desc, signups: c.signups, roster,
    fromInitiative: null, order: ci
  };
});

// ---- inventory -----------------------------------------------------------
const INV = [
  ['SCI-MIC-400','Compound microscope, 400x','Science Lab','unit',18,12,24,'S-Wing stockroom','Carolina Biological',142.00,'2026-09-02',['SCI-118','SCI-210']],
  ['SCI-FPK-020','Fingerprint lifting kit','Science Lab','kit',7,15,40,'S-Wing stockroom','Carolina Biological',23.50,'2026-09-08',['SCI-210']],
  ['SCI-GLV-NIT','Nitrile gloves, box of 100','Science Lab','box',9,14,36,'S-Wing stockroom','School Health Supply',11.20,'2026-09-08',['SCI-210','SCI-118']],
  ['SCI-GOG-STD','Safety goggles, student','Science Lab','unit',62,40,80,'S-Wing stockroom','Carolina Biological',6.40,'2026-08-28',['SCI-210','SCI-118']],
  ['SCI-SLD-BLK','Blank microscope slides, 72 ct','Science Lab','box',21,10,28,'S-Wing stockroom','Carolina Biological',9.75,'2026-08-28',['SCI-118']],
  ['MAT-CAL-GRA','Graphing calculator, TI-84','Mathematics','unit',6,15,40,'M-Wing cart 2','Central District Warehouse',96.00,'2026-09-05',['MAT-150','MAT-210']],
  ['MAT-CMP-GEO','Geometry compass set','Mathematics','set',34,20,48,'M-Wing cart 2','Central District Warehouse',4.10,'2026-08-21',['MAT-210']],
  ['MAT-GRD-PAD','Graph paper pad, 50 sheet','Mathematics','pad',48,30,90,'Main supply room','Central District Warehouse',2.35,'2026-08-21',['MAT-150','MAT-210']],
  ['ART-CLY-STO','Stoneware clay, 25 lb','Arts','block',11,16,44,'Kiln room','Sax Arts & Crafts',18.90,'2026-09-09',['ART-140']],
  ['ART-GLZ-CLR','Glaze, cone 6 assorted pint','Arts','pint',26,12,32,'Kiln room','Sax Arts & Crafts',14.25,'2026-09-09',['ART-140']],
  ['ART-CAM-DSL','Loaner DSLR body','Arts','unit',8,10,20,'A-114 cabinet','B&H Education',379.00,'2026-09-04',['ART-112']],
  ['ART-SDC-64G','SD card, 64 GB','Arts','unit',13,12,30,'A-114 cabinet','B&H Education',12.80,'2026-09-04',['ART-112']],
  ['TEC-KIT-VEX','Robotics kit, competition','Career & Tech','kit',5,8,18,'T-108 bench','VEX Robotics',329.00,'2026-09-06',['CTE-118']],
  ['TEC-SRV-STD','Standard servo motor','Career & Tech','unit',22,24,60,'T-108 bench','VEX Robotics',13.40,'2026-09-06',['CTE-118']],
  ['TEC-HDS-USB','Headset, USB wired','Technology','unit',14,16,24,'T-102 lab','Central District Warehouse',31.00,'2026-09-01',['TEC-130']],
  ['TEC-MSE-GAM','Gaming mouse','Technology','unit',9,10,20,'T-102 lab','Central District Warehouse',27.50,'2026-09-01',['TEC-130']],
  ['CUL-APR-STD','Kitchen apron, student','Career & Tech','unit',18,14,32,'C-101 pantry','WebstaurantStore',9.60,'2026-08-30',['CTE-122']],
  ['CUL-KNF-CHF','Chef knife, 8 in','Career & Tech','unit',16,12,20,'C-101 locked drawer','WebstaurantStore',21.75,'2026-08-30',['CTE-122']],
  ['PE-HRN-CLB','Climbing harness, youth','Athletics','unit',12,14,24,'Gym annex cage','Petzl Education',58.00,'2026-09-07',['PE-160']],
  ['PE-CHK-BAG','Chalk bag','Athletics','unit',19,10,24,'Gym annex cage','Petzl Education',12.00,'2026-09-07',['PE-160']],
  ['MUS-RED-ALT','Alto sax reed, box of 10','Arts','box',15,8,24,'A-101 storage','Woodwind & Brasswind',27.90,'2026-08-25',['MUS-105']],
  ['GEN-PPR-CAS','Copy paper, case of 10 ream','Facilities','case',31,20,60,'Main supply room','Central District Warehouse',42.00,'2026-09-10',[]],
  ['GEN-WBM-DRY','Dry-erase marker, 12 ct','Facilities','box',44,25,70,'Main supply room','Central District Warehouse',8.15,'2026-09-10',[]],
  ['GEN-CHR-STD','Student chair, stackable','Facilities','unit',46,30,60,'Receiving dock','Central District Warehouse',54.00,'2026-08-18',[]]
];

// ---- initiatives ---------------------------------------------------------
const INITS = [
  {id:'INIT-01', title:'Sunrise Coding Club', kind:'Club', proposedBy:'M. Delacroix, Career & Tech', interest:94, askCapacity:30, status:'proposed', window:'Tue/Thu 7:15a', note:'Students want a before-school build session; robotics waitlist is the main feeder.', source:'September interest survey'},
  {id:'INIT-02', title:'Second section of Forensic Science', kind:'Course section', proposedBy:'R. Okonkwo, Science', interest:88, askCapacity:24, status:'proposed', window:'Period 6', note:'Waitlist already exceeds a full section. Lab bench capacity is the constraint, not staffing.', source:'Waitlist rollover'},
  {id:'INIT-03', title:'Student Podcast Studio', kind:'Program', proposedBy:'T. Ellery, Humanities', interest:71, askCapacity:16, status:'piloting', window:'Period 7', note:'Pilot running in E-118 with borrowed mics; needs a permanent room to scale.', source:'September interest survey'},
  {id:'INIT-04', title:'Climbing Team (competitive)', kind:'Club', proposedBy:'D. Boone, Athletics', interest:63, askCapacity:20, status:'proposed', window:'After school, M/W', note:'Rock Climbing filled in four days with nine still waiting; a team gives the overflow somewhere to go.', source:'Waitlist rollover'},
  {id:'INIT-05', title:'Spanish Conversation Table', kind:'Program', proposedBy:'C. Quintero, Humanities', interest:38, askCapacity:24, status:'proposed', window:'Lunch, Fridays', note:'Low-cost, no room conflict. Would run in the cafeteria alcove.', source:'Teacher proposal'},
  {id:'INIT-06', title:'Repair Cafe (fix-it workshop)', kind:'Club', proposedBy:'J. Whitfield, Technology', interest:29, askCapacity:18, status:'proposed', window:'After school, Thu', note:'Families bring broken small appliances; students diagnose under supervision.', source:'Family night feedback'},
  {id:'INIT-07', title:'Morning Jazz Combo', kind:'Course section', proposedBy:'P. Sandoval, Arts', interest:17, askCapacity:12, status:'shelved', window:'Period 0', note:'Shelved for Fall: only seventeen signals and Jazz Band still has open seats.', source:'September interest survey'}
];

// ---- campaigns -----------------------------------------------------------
const CAMPAIGNS = [
  {id:'CMP-01', target:'TEC-130', targetKind:'course', headline:'Build it, then compete: Esports & Game Design has a waitlist', channel:'Morning bulletin', starts:'2026-09-08', ends:'2026-09-19', status:'running', note:'Pointing overflow toward the Repair Cafe and coding club.'},
  {id:'CMP-02', target:'SOC-130', targetKind:'course', headline:'Thirteen seats left in Model UN — two conferences this spring', channel:'Homeroom slide', starts:'2026-09-09', ends:'2026-09-26', status:'running', note:'Under-enrolled; conference registration closes in October.'}
];

// ---- write files ---------------------------------------------------------
const files = [];
function put(collection, docId, body) {
  const fname = (collection + '__' + docId).replace(/[^A-Za-z0-9_.-]/g, '_') + '.json';
  fs.writeFileSync(path.join(OUT, fname), JSON.stringify(body, null, 1));
  files.push({op: 'set', collection, doc_id: docId, file_path: path.join(OUT, fname)});
}

courseDocs.forEach(c => put('courses', c.code, c));
INV.forEach(r => put('inventory', r[0], {
  sku:r[0], name:r[1], category:r[2], unit:r[3], onHand:r[4], reorderPoint:r[5],
  par:r[6], location:r[7], supplier:r[8], unitCost:r[9], lastCounted:r[10], linkedCourses:r[11],
  requisitioned: false
}));
INITS.forEach(i => put('initiatives', i.id, i));
CAMPAIGNS.forEach(c => put('campaigns', c.id, c));
put('catalog', 'students', {list: students, updated: '2026-09-11'});
put('meta', 'school', {
  name: 'Halverson Ridge Middle School', shortName: 'Halverson Ridge',
  term: 'Fall 2026', grades: '6–8', week: 5, weekOf: '2026-09-07',
  registrar: 'Office of the Registrar', enrollmentTotal: students.length,
  addDropCloses: '2026-09-25'
});
put('meta', 'activity', {entries: [
  {at:'2026-09-11T15:20:00Z', text:'Waitlist for Forensic Science passed a full section (19).', kind:'demand'},
  {at:'2026-09-11T11:02:00Z', text:'Fingerprint lifting kit fell below reorder point (7 of 15).', kind:'inventory'},
  {at:'2026-09-10T14:41:00Z', text:'Copy paper counted: 31 cases on hand.', kind:'inventory'},
  {at:'2026-09-09T09:15:00Z', text:'Campaign "Thirteen seats left in Model UN" started on Homeroom slide.', kind:'promotion'}
]});

fs.writeFileSync(path.join(__dirname, 'batch.json'), JSON.stringify(files, null, 1));
console.log('docs:', files.length);
console.log('largest doc bytes:', Math.max(...files.map(f => fs.statSync(f.file_path).size)));
console.log('roster totals:', courseDocs.map(c => c.code + ':' + c.roster.filter(r=>r.state==='enrolled').length + '/' + c.capacity + '+' + c.roster.filter(r=>r.state==='waitlist').length).join('  '));
