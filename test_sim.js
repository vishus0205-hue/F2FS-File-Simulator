const fs = require('fs');
const code = fs.readFileSync('app.js', 'utf8');

// Mock browser objects
global.document = {
  createElement: (tag) => ({
    className: '',
    id: '',
    title: '',
    textContent: '',
    innerHTML: '',
    appendChild: () => {},
    querySelector: () => ({ appendChild: () => {} }),
    querySelectorAll: () => []
  }),
  getElementById: (id) => ({
    textContent: '',
    innerHTML: '',
    classList: { add: () => {}, remove: () => {} },
    appendChild: () => {},
    querySelector: () => ({ appendChild: () => {} }),
    addEventListener: () => {}
  }),
  querySelectorAll: () => [],
  addEventListener: () => {}
};
global.window = global;

eval(code);

console.log('Testing 300 write operations...');
try {
  initSimulation(90);
  for (let i = 0; i < 300; i++) {
    performSingleWrite(false);
  }
  console.log('300 writes completed successfully!');
  console.log('Final WAF:', (activeFS.physicalWrites / activeFS.logicalWrites).toFixed(4));
  console.log('Erases:', flashDevice.getTotalErases());
} catch (e) {
  console.error('ERROR OCCURRED:', e);
}
