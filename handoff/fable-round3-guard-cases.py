from h import *
A = "  'use strict';\n  var CFG = __IKE_CFG__;\n"
B = "  install(window);\n"
show("directive defeat", real("(function () {\n  'use strict';\n", "", old=OLD) or guard.file_problems(NAME, OLD, OLD.replace("(function () {\n  'use strict';\n", "(function () {\n  0;\n  'use strict';\n",1)))
show("implicit throw top", real(B, "  var zz = ({}).a.b;\n", after=False))
show("implicit throw gated", real(B, "  if (screen.width === 1600) { var zz = ({}).a.b; }\n", after=False))
show("null call", real(B, "  var zf = 0; zf();\n", after=False))
show("new fn throw called", real(B, "  function boom() { throw 1; }\n  boom();\n", after=False))
show("recursion", real(B, "  function rr() { rr(); }\n  rr();\n", after=False))
show("wrap charCodeAt", real(B, "  wrap(String.prototype, 'charCodeAt', function (orig) { return function () { return 0; }; });\n", after=False))
show("cores 6 gate", real(B, "  if (navigator.hardwareConcurrency === 6) { var q1 = 1; }\n", after=False))
show("tz gate", real(B, "  if (Intl.DateTimeFormat().resolvedOptions().timeZone === 'Europe/Berlin') { var q1 = 1; }\n", after=False))
show("call install again", real(B, "  install(window);\n", after=False))
show("new Array(-1)", real(B, "  var za = new Array(-1);\n", after=False))
show("BigInt mix", real(B, "  var zb = 1n + 1;\n", after=False))
show("tdz", real(B, "  { zc; let zc = 1; }\n", after=False))
