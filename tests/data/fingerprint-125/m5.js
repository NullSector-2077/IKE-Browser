import { tag } from './m4dep.js';
onmessage = function (e) { postMessage('got ' + e.data + ' ' + tag); };
postMessage('ready');
