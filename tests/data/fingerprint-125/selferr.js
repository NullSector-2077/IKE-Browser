self.onerror = function (msg, file, line, col, err) { postMessage({ msg: msg, file: file, line: line, col: col, stack: err && String(err.stack) }); return true; };
setTimeout(function () { throw new Error('later'); }, 0);
