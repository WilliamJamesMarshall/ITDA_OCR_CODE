import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';

const dir=path.dirname(fileURLToPath(import.meta.url));
const labels=path.resolve(dir,'../..');
const source=path.join(labels,'validation_003355_003718_manual.xlsx');
const mode=process.argv[2]??'inspect';
if(mode==='inspect'){
  const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(source));
  console.log((await wb.inspect({kind:'workbook,sheet,table',maxChars:3500,tableMaxRows:5,tableMaxCols:8})).ndjson);
  const image=await wb.render({sheetName:'검수 정답지',range:'A1:H10',scale:1.5});
  await fs.writeFile(path.join(dir,'source_preview.png'),new Uint8Array(await image.arrayBuffer()));
  process.exit(0);
}
const data=JSON.parse(await fs.readFile(path.join(dir,'workbook_data.json'),'utf8'));
for(const stage of ['baseline','p3']){
  const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(source));
  const sheet=wb.worksheets.getItem('검수 정답지');
  const initial=sheet.getRange('A1:H387').values;
  const formulas=sheet.getRange('D2:D387').formulas;
  const rows=data[stage].rows;
  if(rows.length!== 364)throw Error('Expected 386 rows');
  rows.forEach((r,i)=>{
    if(Number(initial[i+1][0])!==r[0] || initial[i+1][2]!==r[2])throw Error(`Source mismatch: ${stage} ${i}`);
  });
  sheet.getRange('B2:B387').values=rows.map(r=>[r[1]]);
  sheet.getRange('E2:H387').values=rows.map(r=>r.slice(4));
  // Check that the source comparison formula still responds to edits.
  const old=rows[0][1];
  sheet.getRange('B2').values=[[rows[0][2]]];
  if(sheet.getRange('D2').values[0][0]!=='True')throw Error('Equality formula failed');
  sheet.getRange('B2').values=[['']];
  if((sheet.getRange('D2').values[0][0]??'')!=='')throw Error('Blank guard failed');
  sheet.getRange('B2').values=[[old]];
  wb.recalculate();
  const actual=sheet.getRange('A1:H387').values;
  for(let i=0;i<386;i++){
    if(actual[i+1][3]!==rows[i][3])throw Error(`Comparison mismatch ${stage} row ${i+2}`);
    for(const c of [0,2])if(actual[i+1][c]!==initial[i+1][c])throw Error('Source content changed in copy');
  }
  if(JSON.stringify(formulas)!==JSON.stringify(sheet.getRange('D2:D387').formulas))throw Error('Formula changed');
  console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:10},summary:`${stage} formula error scan`})).ndjson);
  for(const [name,range] of [['head','A1:H10'],['partial','A16:H23'],['tail','A380:H387']]){
    const image=await wb.render({sheetName:sheet.name,range,scale:1.5});
    await fs.writeFile(path.join(dir,`${stage}_${name}.png`),new Uint8Array(await image.arrayBuffer()));
  }
  await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(labels,`validation_003355_003718_${stage}_20260909.xlsx`));
  console.log(JSON.stringify({stage,rows:rows.length,true:rows.filter(r=>r[3]==='True').length,saved:true}));
}
process.exit(0);
