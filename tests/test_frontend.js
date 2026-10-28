const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadHtml(file) {
    const elements = new Map();
    const element = () => ({
        innerHTML: '', textContent: '', value: '', style: {}, children: [], dataset: {},
        classList: { add() {}, remove() {} },
        addEventListener() {}, querySelectorAll() { return []; },
        appendChild(child) { this.children.push(child); },
        setAttribute(name, value) { this[name] = value; },
        showModal() { this.open = true; },
        close() { this.open = false; },
    });
    const document = {
        getElementById(id) {
            if (!elements.has(id)) elements.set(id, element());
            return elements.get(id);
        },
        createElement: element,
        addEventListener() {},
        querySelectorAll() { return []; },
    };
    class SourceOnlyDate extends Date {
        constructor(...args) {
            assert(args.length > 0, 'Page must not substitute viewing time for source date');
            super(...args);
        }
    }
    const context = vm.createContext({
        document, window: { addEventListener() {} }, Date: SourceOnlyDate,
    });
    const html = fs.readFileSync(file, 'utf8');
    for (const match of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) {
        vm.runInContext(match[1], context, { filename: file });
    }
    return { context, elements };
}

const home = loadHtml(path.join(__dirname, '..', 'docs', 'index.html'));
home.context.displayEtfData({
    date: '20260601', updated_at: '2026-06-01T13:00:00Z',
    missing_share_etfs: ['00400A'], etfs: { AAA: { name: 'A' }, '00400A': { name: '國泰測試基金' } },
});
assert.match(home.elements.get('status').innerHTML, /2026\/06\/01/);
assert.equal(home.elements.get('last-update').textContent,
    new Date('2026-06-01T13:00:00Z').toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' }));
assert.match(home.elements.get('reports').children[0].textContent, /00400A/);
assert.match(home.elements.get('reports').innerHTML, /已載入 2 筆/);
home.context.setFundFilter('missing');
assert.match(home.elements.get('etf-summary').innerHTML, /國泰測試基金/);
assert.equal(home.elements.get('result-count').textContent, '顯示 1 / 2 檔基金');
home.context.setFundFilter('complete');
assert.doesNotMatch(home.elements.get('etf-summary').innerHTML, /國泰測試基金/);
home.context.setFundFilter('all');
home.elements.get('fund-search').value = '不存在';
home.context.renderFunds();
assert.match(home.elements.get('etf-summary').innerHTML, /找不到符合條件/);
home.elements.get('fund-search').value = '';

home.context.displayEtfData({ AAA: { name: 'legacy' } });
assert.match(home.elements.get('status').innerHTML, /未提供/);
assert.equal(home.elements.get('last-update').textContent, '未提供');

home.context.displayEtfData({ date: '20260601', updated_at: 'invalid', etfs: {} });
assert.equal(home.elements.get('last-update').textContent, '2026/06/01（未提供更新時間）');

const saved = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'docs', 'data', 'active_etf_summary.json'), 'utf8'));
home.context.displayEtfData(saved);
assert.match(home.elements.get('status').innerHTML, new RegExp(saved.date.slice(0, 4)));

if (process.argv[2]) {
    const report = loadHtml(process.argv[2]);
    report.context.window.__STOCK_HISTORY = {
        '2330': [{ date: '20260601', '總股數': 1000, '收盤價': 100 }],
    };
    report.context.openStockModal('2330');
    assert.match(report.elements.get('modalBody').innerHTML, /100,000\.00/);
    report.context.window.__STOCK_HISTORY['2330'] = [
        { date: '20260601', '總股數': 2000, '收盤價': 100 },
        { date: '20260528', '總股數': 1000, '收盤價': null },
    ];
    report.context.openStockModal('2330');
    assert.match(report.elements.get('modalBody').innerHTML, /<td class='num'>-<\/td><td class='num'>-<\/td>/);
}
async function testAiAnalysis() {
    const result = {
        stock: '<script>alert(1)</script>', horizon: '未來三個月', model: 'test-model',
        generated_at: '2026-10-28T20:00:00+08:00',
        blocks: [{ segments: [{ text: '<img src=x onerror=alert(1)>' },
            { text: '證交所來源', url: 'https://www.twse.com.tw/' }, { text: '不安全連結', url: 'javascript:alert(1)' }] }],
        sources: [{ title: '證交所', url: 'https://www.twse.com.tw/' }],
        search_suggestions: '<div>Google 搜尋建議</div><script>untrusted()</script>',
    };
    home.context.renderAnalysis(result);
    const rendered = home.elements.get('ai-result').innerHTML;
    assert.match(rendered, /&lt;script&gt;/);
    assert.doesNotMatch(rendered, /<script>|<img|href="javascript:/);
    assert.match(rendered, /href="https:\/\/www.twse.com.tw\/"/);
    assert.match(rendered, /title="Google 搜尋建議"/);
    assert.match(rendered, /sandbox="allow-popups allow-popups-to-escape-sandbox"/);
    assert.doesNotMatch(rendered, /allow-scripts|allow-same-origin/);
    assert.match(rendered, /基本|未來三個月/);
    home.context.AbortController = AbortController;
    home.context.setTimeout = setTimeout;
    home.context.clearTimeout = clearTimeout;
    const form = home.context.document;
    form.getElementById('ai-stock').value = '';
    await home.context.analyzeStock();
    assert.match(home.elements.get('ai-status').textContent, /請先輸入/);
    form.getElementById('ai-stock').value = '2330';
    form.getElementById('ai-horizon').value = '3m';
    home.context.fetch = async () => ({ ok: false, headers: { get: () => 'application/json' },
        json: async () => ({ error: '尚未設定 AI 金鑰' }) });
    await home.context.analyzeStock();
    assert.match(home.elements.get('ai-status').textContent, /尚未設定 AI 金鑰/);
    assert.equal(home.elements.get('ai-result').innerHTML, '');
    assert.equal(home.elements.get('ai-submit').disabled, false);
    home.context.fetch = async (url, options) => {
        assert.equal(url, '/api/analyze-stock');
        assert.deepEqual(JSON.parse(options.body), { stock: '2330', horizon: '3m' });
        return { ok: true, headers: { get: () => 'application/json' }, json: async () => result };
    };
    await home.context.analyzeStock();
    assert.equal(home.elements.get('ai-status').dataset.state, 'ready');
    assert.equal(home.elements.get('ai-submit').disabled, false);
    assert.match(home.elements.get('ai-result').innerHTML, /參考來源/);
    const details = { code:'00980A', name:'測試基金', asof:'20260601', previous_date:'20260528', comparable:true,
        added_shares:1500, reduced_shares:0, comparison_note:'快照差異不是成交紀錄', profit_note:'基金成本未提供',
        holdings:[{code:'2330',name:'台積電',shares:2500,lot_size:1000,weight:'5%'}],
        changes:[{code:'2330',name:'台積電',previous_shares:1000,shares:2500,delta_shares:1500,delta_lots:1.5}],
    };
    home.context.fetch = async url => ({ok:true,headers:{get:()=> 'application/json'},json:async()=> url.endsWith('/market')
        ? {quote:{close:23.5,date:'20261027'},dividend_status:'ok',dividend_period:'2025–2026',dividends:[{ex_date:'115年08月18日',record_date:'115年08月24日',pay_date:'115年09月11日',cash_per_unit:0.638}]}
        : details});
    await home.context.openEtfDetails('00980A');
    await home.context.loadEtfMarket('00980A', vm.runInContext('etfRequest', home.context));
    assert.equal(home.elements.get('etf-dialog').open, true);
    assert.match(home.elements.get('detail-date').textContent, /2026\/06\/01/);
    assert.match(home.elements.get('detail-changes-table').innerHTML, /1.5/);
    assert.match(home.elements.get('detail-dividends-table').innerHTML, /0.638/);
    assert.equal(home.elements.get('detail-close-price').textContent,'23.5');
    home.context.selectDetailTab('profit');
    assert.equal(home.elements.get('detail-profit').hidden,false);
    form.getElementById('profit-lots').value = '1';
    form.getElementById('profit-cost').value = '20';
    form.getElementById('profit-price').value = '23.5';
    form.getElementById('profit-dividends').value = '638';
    home.context.calculateEtfProfit();
    assert.match(home.elements.get('profit-output').innerHTML,/4,138/);
    assert.match(home.elements.get('profit-output').innerHTML,/20.69/);
    form.getElementById('profit-cost').value = '0';
    home.context.calculateEtfProfit();
    assert.match(home.elements.get('profit-output').textContent,/請輸入有效/);
    home.context.fetch = async () => ({ok:false,headers:{get:()=> 'application/json'},json:async()=>({error:'尚未設定 AI 金鑰'})});
    form.getElementById('detail-horizon').value = '3m';
    await home.context.analyzeEtfTrend();
    assert.match(home.elements.get('detail-ai-status').textContent,/尚未設定 AI 金鑰/);
    home.context.closeEtfDetails();
    assert.equal(home.elements.get('etf-dialog').open,false);
    console.log('Frontend regressions passed: ETF dialog, snapshot changes, profit, dividends, dates, filters, AI and escaping.');
}
testAiAnalysis().catch(error => { console.error(error); process.exitCode = 1; });
