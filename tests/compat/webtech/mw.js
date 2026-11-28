self.onmessage = (e) => self.postMessage({ echo: e.data, module: true, href: self.location.href });
