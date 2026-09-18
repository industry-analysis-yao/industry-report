// No browser or dependencies required: check actual card output and routing.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const html = fs.readFileSync('index.html', 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m => m[1]);
scripts.forEach(code => new vm.Script(code));
const code = scripts.join('\n');
const names = ['dailyNewsSection', 'getTypeBadgeClass', 'getCatColor', 'buildCard'];
const extracted = names.map(name => code.match(new RegExp('function ' + name + '\\([^]*?\\n\\}'))[0]).join('\n');
const context = vm.createContext({});
vm.runInContext(extracted, context);
const date = process.argv[2] || JSON.parse(fs.readFileSync('data/dates_index.json', 'utf8'))[0];
const data = JSON.parse(fs.readFileSync(`data/${date}.json`, 'utf8'));
const counts = {};
data.items.forEach((item, i) => {
  const section = context.dailyNewsSection(item);
  assert.equal(section, item.dashboard_section);
  counts[section] = (counts[section] || 0) + 1;
  const card = context.buildCard(item, i);
  assert(card.includes('原文公開日: ' + item.date));
  if (item.summary_method === 'publisher_excerpt') assert(card.includes('AI要約ではありません'));
  if (item.summary_method === 'codex_editorial') {
    assert(card.includes('Codex編集要約（原文照合）'));
    assert(card.includes('出典確認・日付・注意事項'));
  }
});
assert.equal(Object.values(counts).reduce((a,b) => a+b, 0), data.items.length);
assert.deepEqual(counts, data.selection_health.section_counts);
assert.equal(context.dailyNewsSection({title:'wet wipe packaging machine automation',category_id:'④'}),'packaging');
assert.equal(context.dailyNewsSection({title:'wet tissue new product',category_id:'⑥'}),'wet');
assert.equal(context.dailyNewsSection({title:'ピッキング表示器 発売',category_id:'④'}),'palletizer');
assert.equal(context.dailyNewsSection({title:'包装機とロボット',category_id:'④', summary_method:'codex_editorial', dashboard_section:'packaging'}),'packaging');
for (const patent of data.new_patents || []) {
  const card = context.buildCard(patent, patent.id);
  assert(card.includes('公開日: ' + patent.date));
  assert(card.includes('出願日: ' + patent.application_date));
  assert(card.includes('登録日: 未確認'));
  assert(card.includes(patent.publication_number));
}
if (data.edition_counts) {
  assert.equal(data.edition_counts.news, data.items.length);
  assert.equal(data.edition_counts.new_patents, data.new_patents.length);
  assert.equal(data.edition_counts.total, data.items.length + data.new_patents.length);
}
assert(!context.buildCard({title:'<img src=x onerror=alert(1)>', url:'javascript:alert(1)'}, 0).includes('<img'));
assert(!context.buildCard({url:'javascript:alert(1)'}, 0).includes('href="javascript:'));
console.log(`Frontend syntax, ${data.items.length} card strings and exclusive counts OK`, counts);
