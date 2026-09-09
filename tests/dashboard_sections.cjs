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
});
assert.equal(Object.values(counts).reduce((a,b) => a+b, 0), data.items.length);
assert.deepEqual(counts, data.selection_health.section_counts);
assert.equal(context.dailyNewsSection({title:'wet wipe packaging machine automation',category_id:'④'}),'packaging');
assert.equal(context.dailyNewsSection({title:'wet tissue new product',category_id:'⑥'}),'wet');
assert.equal(context.dailyNewsSection({title:'ピッキング表示器 発売',category_id:'④'}),'palletizer');
console.log(`Frontend syntax, ${data.items.length} card strings and exclusive counts OK`, counts);
