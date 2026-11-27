# Scenarios adapted from Dark Reader's tests (MIT, https://github.com/darkreader/darkreader).
# Copyright (c) Alexander Shutau and contributors. The licence text is in LICENSE.darkreader
# (same folder). Only scenario content (HTML/CSS/setup steps) is reproduced; no engine source.
#
# Each fixture: id, title, html (body content), optional script (runs after the dark engine
# started), optional pre_script (runs at DOMContentLoaded, before the engine), fix (Dark Reader
# fix object or None), checks (selectors of inspected elements, plus "html"), theme_specific,
# optional skip (reason). Extra key "shadow_checks": selectors resolved INSIDE the open shadow
# root of the first ".shadow-dom-wrapper" / "custom-element" host (not reachable by `checks`).
import base64
import re
import urllib.parse


def ml(*lines):
    """Same as the tests' multiline(): join lines, ensure a trailing newline."""
    lines = list(lines)
    if not lines or lines[-1] != '':
        lines.append('')
    return '\n'.join(lines)


def enc(s):
    return urllib.parse.quote(s, safe="-_.!~*'()")


def svg_url(svg):
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()


def css_url(css):
    return 'data:text/css;utf8,' + enc(css)


def wait(ms=0):
    return 'await new Promise(r=>setTimeout(r, %d));' % ms


def A(*code):
    return '(async () => {\n' + '\n'.join(code) + '\n})();'


def slug(t):
    s = re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')
    return s[:60].strip('-')


FIXTURES = []
_ids = set()


def fx(stem, title, html='', script=None, pre_script=None, fix=None, checks=(),
       theme_specific=False, skip=None, shadow_checks=None, slug_override=None):
    base = '%s/%s' % (stem, slug_override or slug(title))
    i, n = base, 2
    while i in _ids:
        i = '%s-%d' % (base, n)
        n += 1
    _ids.add(i)
    ck = list(dict.fromkeys(list(checks) + ['html']))
    d = {'id': i, 'title': title, 'html': html, 'fix': fix, 'checks': ck,
         'theme_specific': theme_specific}
    if script:
        d['script'] = script
    if pre_script:
        d['pre_script'] = pre_script
    if shadow_checks:
        d['shadow_checks'] = list(shadow_checks)
    if skip:
        d['skip'] = skip
    FIXTURES.append(d)


def fixobj(invert=(), css='', ignoreInlineStyle=(), ignoreImageAnalysis=()):
    return {'invert': list(invert), 'css': css,
            'ignoreInlineStyle': list(ignoreInlineStyle),
            'ignoreImageAnalysis': list(ignoreImageAnalysis)}


API_SKIP = 'tests an internal JS API / returned object, not rendered colours'
REMOTE_SKIP = 'needs a cross-origin server (echo URL) and extension background fetch stub'
TOGGLE_SKIP = 'requires removing/re-enabling or reconfiguring the engine itself'
INTERNAL_SKIP = 'manipulates the engine\'s own injected override element'

# ---------------------------------------------------------------- color
S = 'color'
fx(S, 'should modify RGBA', ml(
    '<style>',
    '    h1 { background: rgb(245, 185, 124); }',
    '    h1 strong { color: rgb(34, 52, 34); }',
    '    body { background-color: rgba(51, 170, 51, .4); }',
    '</style>',
    '<h1>RGB <strong>Power</strong>!</h1>'), checks=['body', 'h1', 'h1 strong'])
fx(S, 'should modify HSL', ml(
    '<style>',
    '    h1 { background: hsl(270,60%,70%); }',
    '    h1 strong { color: hsl(.75turn, 60%, 70%); }',
    '    body { background-color: hsl(4.71239rad, 60%, 70%); }',
    '</style>',
    '<h1>HSL <strong>Power</strong>!</h1>'), checks=['body', 'h1', 'h1 strong'])
fx(S, 'should modify HSLA', ml(
    '<style>',
    '    h1 { background: hsla(240, 100%, 50%, .7); }',
    '    h1 strong { color: hsla(240, 100%, 50%, 1); }',
    '    body { background-color: hsla(240, 100%, 50%, .05); }',
    '</style>',
    '<h1>HSLA <strong>Power</strong>!</h1>'), checks=['body', 'h1', 'h1 strong'])
fx(S, 'should modify knownColors', ml(
    '<style>',
    '    h1 { background: rebeccapurple; }',
    '    h1 strong { color: InfoBackground; }',
    '    body { background-color: transparent; }',
    '</style>',
    '<h1>Weird color <strong>Power</strong>!</h1>'), checks=['body', 'h1', 'h1 strong'])
fx(S, 'should handle calc(...) cases', ml(
    '<style>',
    '    h1 { background-color: hsl(0, 0%, calc(95% - 3%)) }',
    '</style>',
    '<h1>Weird color <strong>Power</strong>!</h1>'), checks=['h1'])
fx(S, "should handle gradient's cases with rgb(...) xx%", ml(
    '<style>',
    '    h1 { background-image: -webkit-linear-gradient(bottom, rgb(255, 255, 255) 15%, rgb(246, 246, 245) 85%); }',
    '</style>',
    '<h1>Weird color <strong>Power</strong>!</h1>'), checks=['h1'])
fx(S, 'should handle complex calc(...) cases', ml(
    '<style>',
    '    h1 { background-color: rgb(calc(216.75 + 153 * .15), calc(216.75 + 205 * .15), calc(216.75 + 255 * .15)) }',
    '</style>',
    '<h1>Weird color <strong>Power</strong>!</h1>'), checks=['h1'])
fx(S, 'should handle gradients with calc(...) cases', ml(
    '<style>',
    '    h1 { background-image: linear-gradient(rgb(249, 249, 251) calc(100% - 3px), transparent), linear-gradient(-90deg, rgb(255, 145, 0), rgb(241, 3, 102) 50%, rgb(97, 115, 255)) }',
    '</style>',
    '<h1>Weird color <strong>Power</strong>!</h1>'), checks=['h1'])
fx(S, 'should update when colors change', ml(
    '<style>',
    '    h1 { background-color: rgb(255, 255, 255); }',
    '</style>',
    '<h1>Colors update</h1>'), fix=fixobj(), checks=['h1'], theme_specific=True)
# (the original starts with darkSchemeBackgroundColor #111111 then updates it to #111213 at
# runtime; the second step cannot be scripted from the page)

# ---------------------------------------------------------------- fixes
S = 'fixes'
fx(S, 'should add custom attributes to root element', '', checks=[], theme_specific=True,
   skip='tests Dark Reader-specific data-darkreader-* root attributes and a runtime mode switch')
fx(S, 'should invert selectors', ml('<div class="logo">Some logo</div>'),
   fix=fixobj(invert=['.logo']), checks=['.logo'])
fx(S, 'should insert CSS', ml('<p class="text">Some text need to be red</p>'),
   fix=fixobj(css='.text { color: red }'), checks=['.text'])
fx(S, 'should ignore inline style',
   ml('<p class="text" style="background-color: purple">Some text need to be red</p>'),
   fix=fixobj(ignoreInlineStyle=['.text']), checks=['.text'])
fx(S, 'should ignore styling when darkreader-lock detected', ml(
    '<style>',
    '    body {',
    '        background-color: pink !important;',
    '    }',
    '</style>'),
   pre_script="(function(){var m=document.createElement('meta');m.name='darkreader-lock';document.head.appendChild(m);})();",
   checks=['body'])
fx(S, 'should ignore styling when delayed darkreader-lock detected', ml(
    '<style>',
    '    body {',
    '        background-color: pink !important;',
    '    }',
    '</style>'),
   script=A("const m=document.createElement('meta');m.name='darkreader-lock';",
            'document.head.appendChild(m);', wait(100)),
   checks=['body'])

# ---------------------------------------------------------------- image-analysis
S = 'image-analysis'


def img_css(svg, w, h, sel):
    return ml(
        '%s {' % sel,
        '    background-image: url("%s");' % svg_url(svg),
        '    background-position: center;',
        '    background-repeat: no-repeat;',
        '    background-size: cover;',
        '    display: inline-block;',
        '    height: %dpx;' % h,
        '    width: %dpx;' % w,
        '}')


IMG = {
    'darkIcon': ml('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8" width="8" height="8">',
                   '    <rect fill="black" width="100%" height="100%" />',
                   '    <rect fill="#444" width="50%" height="50%" />', '</svg>'),
    'lightIcon': ml('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8" width="8" height="8">',
                    '    <rect fill="white" width="100%" height="100%" />',
                    '    <rect fill="#aaa" width="50%" height="50%" />', '</svg>'),
    'darkTransparentIcon': ml('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8" width="8" height="8">',
                              '    <circle fill="black" cx="4" cy="4" r="3" />', '</svg>'),
    'lightTransparentIcon': ml('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8" width="8" height="8">',
                               '    <circle fill="white" cx="4" cy="4" r="3" />', '</svg>'),
    'largeDarkImage': ml('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8" width="1024" height="1024">',
                         '    <rect fill="black" width="100%" height="100%" />',
                         '    <rect fill="#444" width="50%" height="50%" />', '</svg>'),
    'largeLightImage': ml('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8" width="1024" height="1024">',
                          '    <rect fill="white" width="100%" height="100%" />',
                          '    <rect fill="#aaa" width="50%" height="50%" />', '</svg>'),
}
for t in ['should analyze dark icon', 'should analyze light icon',
          'should analyze dark transparent icon',
          'should use viewBox size for SVG without width and height',
          'should use viewBox size for SVG with XML declaration',
          'should use viewBox size for SVG with leading comment',
          'should use viewBox size for SVG with leading whitespace',
          'should use viewBox size for SVG with stroke-width on root element',
          'should not use viewBox size for SVG with width and height',
          'should not analyze large image']:
    fx(S, t, '', checks=[], skip=API_SKIP + ' (getImageDetails)')

fx(S, 'should invert dark icons', ml(
    '<style>', img_css(IMG['darkTransparentIcon'], 16, 16, 'i'), '</style>',
    '<h1>Dark icon <i></i></h1>'), checks=['i'])
fx(S, 'should not invert light icons', ml(
    '<style>', img_css(IMG['lightTransparentIcon'], 16, 16, 'i'), '</style>',
    '<h1>Light icon <i></i></h1>'), checks=['i'])
fx(S, 'should not invert dark backgrounds', ml(
    '<style>', img_css(IMG['largeDarkImage'], 320, 320, 'h1'), '</style>',
    '<h1>Dark background</h1>'), checks=['h1'])
fx(S, 'should hide light backgrounds', ml(
    '<style>', img_css(IMG['largeLightImage'], 320, 320, 'h1'), '</style>',
    '<h1>Light background</h1>'), checks=['h1'])
fx(S, 'should ignore image analysis', ml(
    '<style>', img_css(IMG['darkTransparentIcon'], 16, 16, 'i'), '</style>',
    '<h1>Dark icon <i></i></h1>'), fix=fixobj(ignoreImageAnalysis=['*']), checks=['i'])
fx(S, 'should handle background-image with URL and gradient', ml(
    '<style>',
    '    h1 { background-image: url("%s"), linear-gradient(red, white);' % svg_url(IMG['lightIcon']),
    '</style>',
    '<h1>Weird color <strong>Power</strong>!</h1>'), checks=['h1'])
fx(S, 'should handle background-image with non-base64 data URL', ml(
    '<style>',
    """    h1 { background-image: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="6" height="3">%3Cpath%20d%3D%22m0%202.5%20l2%20-1.5%20l1%200%20l2%201.5%20l1%200%22%20stroke%3D%22%23d11%22%20fill%3D%22none%22%20stroke-width%3D%22.7%22%2F%3E</svg>');""",
    '</style>',
    '<h1>Weird color <strong>Power</strong>!</h1>'), checks=['h1'])
fx(S, 'should handle background-image with URL and gradient (revered)', ml(
    '<style>',
    '    h1 { background-image: linear-gradient(red, white), url("%s");' % svg_url(IMG['lightIcon']),
    '</style>',
    '<h1>Weird color <strong>Power</strong>!</h1>'), checks=['h1'])
fx(S, 'should handle background-image with empty URLs', ml(
    '<style>',
    """    h1 { background-image: url(''), url(''), url("%s");""" % svg_url(IMG['lightIcon']),
    '</style>',
    '<h1>Weird color <strong>Power</strong>!</h1>'), checks=['h1'])
for t in ['should apply filters to dark icons', 'should not apply filters to light icons',
          'should handle icons in @media correctly']:
    fx(S, t, '', checks=['i'], skip=REMOTE_SKIP + ' (cross-origin SVG images)')

# ---------------------------------------------------------------- injection
S = 'injection'
fx(S, 'should inject a queued style when the body becomes available', '', checks=[],
   skip='tests the engine\'s internal injectStyleAway()/style container API')
fx(S, 'should clear queued styles and allow observing a new body', '', checks=[],
   skip='tests the engine\'s internal injectStyleAway()/style container API')

# ---------------------------------------------------------------- inline-override
S = 'inline-override'
fx(S, 'should override inline style', '<span style="color: red;">Inline style override</span>',
   checks=['span'])
fx(S, 'should watch for inline style change', '<span style="color: red;">Watch inline style</span>',
   script=A("document.querySelector('span').style.color = 'green';", wait(0)), checks=['span'])
fx(S, 'should override only a single inline style property', ml(
    '<style>.bg-gray { background: gray; }</style>',
    '<span class="bg-gray" style="color: red;">Inline style override</span>'),
   script=A("document.querySelector('span').style.color = 'green';", wait(0)), checks=['span'])
fx(S, 'should override the bgcolor attribute',
   '<table><tr><td bgcolor="red">Cell with bgcolor</td></tr></table>', checks=['td'])
fx(S, 'should override inline style with unformatted values',
   '<span style="color:rgb(255,0,0,.87)">Unformatted inline style</span>', checks=['span'])
fx(S, 'should override inline value regardless of its position', '\n'.join([
    '<span id="mid" style="font-size:10px;color:rgb(255,0,0,.87)">mid</span>',
    '<span id="start" style="color:rgb(255,0,0,.87)">start</span>']), checks=['#mid', '#start'])
fx(S, 'should override inline shorthand properties',
   '<span style="border-color: red; border-style: solid; border-width: 1px">inline border shorthand</span>',
   checks=['span'])
fx(S, 'should override inline styles after disabling and enabling',
   '<span style="color: red;">Toggle inline style</span>', checks=['span'],
   skip=TOGGLE_SKIP + ' (first-start state is covered by "should override inline style")')
fx(S, 'should clean up the customProp after originial is gone',
   '<span style="color: red;">Watch inline style</span>',
   script=A("document.querySelector('span').style.color = '';", wait(0)), checks=['span'])
fx(S, "shouldn't touch rel=\"mask-icon\"", '<link rel="mask-icon" color="red">',
   checks=['link[rel="mask-icon"]'], slug_override='shouldnt-touch-rel-mask-icon')
fx(S, 'shouldn\'t touch a "none" value for fill',
   '<svg> <rect width="100" height="100" fill="none" /></svg>'
   '<style> rect[width][height] { fill: red }</style>', checks=['rect'],
   slug_override='shouldnt-touch-a-none-value-for-fill')
fx(S, 'should override fill attribute', '<svg><text fill="black">SVG text fill</text></svg>',
   checks=['text'])
fx(S, 'should override stroke attribute',
   '<svg><line x1="0" y1="0" x2="10" y2="10" stroke="black" /></svg>', checks=['line'])
fx(S, 'should override stop-color attribute',
   '<svg><defs><linearGradient><stop offset="0%" stop-color="white" /></linearGradient></defs></svg>',
   checks=['stop'])
fx(S, 'should resolve variable type in SVG stroke attribute', ml(
    '<style>:root { --accent: red; }</style>',
    '<svg><path d="M0,0 L10,10" stroke="var(--accent)" fill="none" /></svg>'), checks=['path'])

# ---------------------------------------------------------------- link-override
S = 'link-override'


def link(css):
    return '<link rel="stylesheet" class="testcase--link" href="%s">' % css_url(css)


fx(S, 'should override same-origin link', link(ml('h1 { background: gray; }', 'h1 strong { color: red; }'))
   + '\n' + ml('<h1>Link <strong>override</strong>!</h1>'), checks=['h1', 'h1 strong'])
for t in ['should override cross-origin link', 'should override cross-origin imports in linked CSS',
          'should override cross-origin imports in linked CSS with capital @import',
          'should override cross-origin link that has already been loaded']:
    fx(S, t, '', checks=['h1', 'h1 strong'], skip=REMOTE_SKIP)
fx(S, 'should remove manager from disabled link',
   link(ml('h1 { background: gray; }', 'h1 strong { color: red; }')) + '\n'
   + ml('<h1>Link <strong>disabled</strong>!</h1>'),
   script=A(wait(50), "document.querySelector('.testcase--link').disabled = true;", wait(0)),
   checks=['h1'])
fx(S, "Shouldn't wait on link that won't be loaded",
   '<link rel="stylesheet" class="testcase--link" data-href="%s">\n' % css_url(ml(
       'h1 { background: green !important; }', 'h1 strong { color: orange !important; }'))
   + ml('<style>', '   h1 { background: gray; }', '</style>',
        '<h1>Link <strong>loading with non-href attribute</strong>!</h1>'),
   checks=['h1'], slug_override='shouldnt-wait-on-link-that-wont-be-loaded')
fx(S, "Shouldn't wait for an empty href link to load",
   '<link rel="stylesheet" class="testcase--link" href="">\n'
   + ml('<style>', '   h1 { background: gray; }', '</style>',
        '<h1>Link <strong>with empty href</strong>!</h1>'),
   checks=['h1'], slug_override='shouldnt-wait-for-an-empty-href-link-to-load')
fx(S, 'should handle styles with @import "..." screen;', '', checks=['h1', 'h1 strong'],
   skip=REMOTE_SKIP, slug_override='should-handle-styles-with-import-screen')
fx(S, 'should handle styles with invalid url(...)', '', checks=['h1', 'h1 strong'],
   skip=REMOTE_SKIP, slug_override='should-handle-styles-with-invalid-url')

# ---------------------------------------------------------------- media-query
S = 'media-query'
H1S = '<h1>Some test foor...... <strong>Oh uhm removing styles :(</strong>!</h1>'
fx(S, 'should not style blacklisted media', ml(
    '<style class="testcase-style">', '    h1 { background: green; }',
    '    h1 strong { color: orange; }', '</style>',
    '<style class="testcase-style-2" media="print">', '    h1 { background: gray; }',
    '    h1 strong { color: red; }', '</style>', H1S), checks=['h1', 'h1 strong'])
fx(S, 'should style lazyloaded media', ml(
    '<style class="testcase-style" media="print">', '    h1 { background: green; }',
    '    h1 strong { color: orange; }', '</style>', H1S),
   script=A("document.querySelector('.testcase-style').media = 'screen';", wait(0)),
   checks=['h1', 'h1 strong'])
fx(S, 'should check for CSS support', ml(
    '<style class="testcase-style">',
    '    @supports (background: green) {', '       h1 { background: green; }', '    }',
    '    @supports (color: orange) {', '       h1 strong { color: orange; }', '    }',
    '    @supports (some-non-existing-prop: some-value) {', '       body { background: pink; }', '    }',
    '</style>', H1S), checks=['body', 'h1', 'h1 strong'])
fx(S, 'should check for CSS @media', ml(
    '<style class="testcase-style">',
    '    @media screen and (min-width: 2px) {', '       h1 { background: green; }', '    }',
    '    @media screen and (min-width: 200000px) {', '       h1 { background: orange; }', '    }',
    '</style>', '<h1>Some test media query i guess</h1>'), checks=['h1'])
fx(S, 'should check for nested CSS @media', ml(
    '<style class="testcase-style">',
    '   @media screen and (min-width: 2px) {', '       @media screen and (min-width: 2px) {',
    '           h1 { background: green; }', '       }', '   }',
    '   @media screen and (min-width: 200000px) {', '       h1 { background: orange; }', '   }',
    '</style>', '<h1>Some test media query i guess</h1>'), checks=['h1'])
fx(S, 'should style print/media query', ml(
    '<style class="testcase-style">', '    h1 { background: green; }',
    '    h1 strong { color: orange; }', '</style>',
    '<style class="testcase-style-2" media="print, screen and (max-width: 9999999px)">',
    '    h1 { background: gray; }', '    h1 strong { color: red; }', '</style>',
    '<h1>Some test foor...... <strong>Oh uh media query :D</strong>!</h1>'),
   checks=['h1', 'h1 strong'])
fx(S, 'should handle same cssText but different media rule', ml(
    '<style class="testcase-style">',
    '   @media screen and (min-width: 200000000000000000000px) {', '       h1 { background: green; }', '   }',
    '   @media screen and (min-width: 4px) {', '       h1 { background: green; }', '   }',
    '</style>', H1S), checks=['h1'])
fx(S, 'should not style blacklisted media and handle uppercase media', ml(
    '<style class="testcase-style">', '    h1 { background: green; }',
    '    h1 strong { color: orange; }', '</style>',
    '<style class="testcase-style-2" media="Print">', '    h1 { background: gray; }',
    '    h1 strong { color: red; }', '</style>', H1S), checks=['h1', 'h1 strong'])
fx(S, 'should handle media query and print', ml(
    '<style class="testcase-style">', '   @media (min-width: 2px), print {',
    '       h1 { background: green; }', '   }', '</style>', H1S), checks=['h1'])

# ---------------------------------------------------------------- shadow-dom
S = 'shadow-dom'
WRAP = ml('<div class="shadow-dom-wrapper"></div>')
SH_STYLE_H1 = """const style = document.createElement('style');
style.classList.add('test-case-style');
shadow.appendChild(style);
style.sheet.insertRule('h1 { color: gray }');
style.sheet.insertRule('strong { color: red }');
const h1 = document.createElement('h1');
h1.appendChild(document.createElement('strong'));
shadow.appendChild(h1);"""
ATT = "const shadow = document.querySelector('.shadow-dom-wrapper').attachShadow({mode: 'open'});"
fx(S, 'should add static overrides', WRAP, pre_script='(function(){' + ATT + '})();',
   checks=['.shadow-dom-wrapper'])
fx(S, 'should override styles', WRAP, pre_script='(function(){\n' + ATT + '\n' + SH_STYLE_H1 + '\n})();',
   checks=['.shadow-dom-wrapper'], shadow_checks=['h1', 'strong'])
fx(S, 'should react to DOM changes', WRAP, pre_script='(function(){' + ATT + '})();',
   script=A(ATT.replace("attachShadow({mode: 'open'})", 'shadowRoot'), SH_STYLE_H1, wait(0)),
   checks=['.shadow-dom-wrapper'], shadow_checks=['h1', 'strong'])
fx(S, 'should override inline styles', WRAP, pre_script='(function(){' + ATT + '})();',
   script=A(ATT.replace("attachShadow({mode: 'open'})", 'shadowRoot'),
            "const p = document.createElement('p');", "p.style.color = 'red';", 'p.textContent = "Inline in shadow";',
            'shadow.appendChild(p);', wait(0)),
   checks=['.shadow-dom-wrapper'], shadow_checks=['p'])
CE = """class %s extends HTMLElement {
    constructor() {
        super();
        const shadowRoot = this.attachShadow({mode: 'open'});
        const style = document.createElement('style');
        style.textContent = 'p { color: pink }';
        const paragraph = document.createElement('p');
        paragraph.textContent = 'Some text content that should be pink.';
        shadowRoot.append(style);
        shadowRoot.append(paragraph);
    }
}
customElements.define('%s', %s);"""
fx(S, 'should handle defined custom elements', ml('<custom-element>', '</custom-element>'),
   pre_script='(function(){\n' + CE % ('CustomElement', 'custom-element', 'CustomElement') + '\n})();',
   checks=['custom-element'], shadow_checks=['p'])
fx(S, 'should react to defined custom elements',
   ml('<delayed-custom-element>', '</delayed-custom-element>'),
   script=A(CE % ('DelayedCustomElement', 'delayed-custom-element', 'DelayedCustomElement'), wait(0)),
   checks=['delayed-custom-element'], shadow_checks=['p'])
fx(S, 'should override styles', WRAP, pre_script='''(function(){
const newRule = new CSSStyleSheet();
newRule.insertRule(':host { --red: red }');
%s
shadow.adoptedStyleSheets = [newRule];
const style = document.createElement('style');
style.classList.add('test-case-style');
shadow.appendChild(style);
style.sheet.insertRule('h1 { color: var(--red) }');
const h1 = document.createElement('h1');
h1.textContent = 'Adopted';
shadow.appendChild(h1);
})();''' % ATT, checks=['.shadow-dom-wrapper'], shadow_checks=['h1'],
   slug_override='should-override-styles-adopted')

# ---------------------------------------------------------------- style-override
S = 'style-override'
fx(S, 'should fill CSSStyleSheet with overridden rules', '', checks=[], skip=API_SKIP + ' (createStyleSheetModifier)')
fx(S, 'should override User Agent style', ml('<span>Text</span>', '<a href="#">Link</a>'),
   checks=['body', 'span', 'a'])
fx(S, 'should override static style', ml(
    '<style>', '    h1 { background: gray; }', '    h1 strong { color: red; }', '</style>',
    '<h1>Style <strong>override</strong>!</h1>'), checks=['body', 'h1', 'h1 strong'])
fx(S, 'should override style with @import', ml(
    '<style>', '    @import "%s";' % css_url('h1 { background: gray; }'),
    '    h1 strong { color: red; }', '</style>',
    '<h1>Style <strong>with @import</strong>!</h1>'), script=A(wait(50)),
   checks=['body', 'h1', 'h1 strong'])
fx(S, 'should override style with @import"..."', ml(
    '<style>', '    @import"%s";' % css_url('h1 { background: gray; }'),
    '    h1 strong { color: red; }', '</style>',
    '<h1>Style <strong>with @import"..."</strong>!</h1>'), script=A(wait(50)),
   checks=['body', 'h1', 'h1 strong'], slug_override='should-override-style-with-import-nospace')
fx(S, 'should restore override', ml(
    '<style class="testcase-style">', '    h1 { color: gray; }', '    h1 strong { color: red; }', '</style>',
    '<h1>Style <strong>override</strong>!</h1>'), checks=['h1', 'h1 strong'],
   skip=INTERNAL_SKIP + ' (removes the engine\'s own sibling style node; initial state is covered by "should override static style")')
fx(S, 'should move override', ml(
    '<style class="testcase-style">', '    h1 { background: gray; }', '    h1 strong { color: red; }', '</style>',
    '<h1>Some test foor...... <strong>Moving styles</strong>!</h1>'),
   script=A("document.body.append(document.querySelector('.testcase-style'));", wait(0)),
   checks=['h1', 'h1 strong'])
fx(S, 'should remove override', ml(
    '<style class="testcase-style">', '    h1 { background: gray; }', '    h1 strong { color: red; }', '</style>',
    H1S),
   script=A("document.querySelector('.testcase-style').remove();", wait(0)),
   checks=['h1', 'h1 strong'])
fx(S, 'should react to updated style', ml(
    '<style class="testcase-style"></style>',
    '<h1>Some test foor...... <strong>Oh uhm a pink background</strong></h1>'),
   script=A("const sheet = document.querySelector('.testcase-style').sheet;",
            "sheet.insertRule('h1 { color: gray }');", "sheet.insertRule('strong { color: red }');",
            "sheet.insertRule('body { background-color: pink }');", wait(0)),
   checks=['body', 'h1', 'h1 strong'])
fx(S, 'should react on style text change', ml(
    '<style class="testcase-style">', '    h1 strong { color: red; }', '</style>',
    '<h1>Style <strong>text change</strong></h1>'),
   script=A("document.querySelector('.testcase-style').textContent = 'h1 strong { color: green; }';", wait(0)),
   checks=['h1 strong'])
fx(S, 'should react to a new style', ml('<h1>Some test foor...... <strong>Oh uhm what?</strong>!</h1>'),
   script=A("const style = document.createElement('style');", "style.classList.add('testcase-style');",
            'document.body.append(style);', "style.sheet.insertRule('h1 { color: pink }');",
            "style.sheet.insertRule('strong { color: orange }');", wait(0)),
   checks=['h1', 'h1 strong'])
fx(S, 'should restore override after container move', ml(
    '<div class="style-container">', '    <style class="testcase-style">',
    '        h1 { background: gray; }', '        h1 { color: green; }', '    </style>', '</div>',
    '<h1>Moving container</h1>'),
   script=A("document.body.append(document.querySelector('.style-container'));", wait(0)),
   checks=['h1'])

# ---------------------------------------------------------------- variables
S = 'variables'
V_H1 = '<h1>CSS <strong>variables</strong>!</h1>'
fx(S, 'should override style with variables', ml(
    '<style>', '    :root {', '        --bg: gray;', '        --text: red;', '    }',
    '    h1 { background: var(--bg); }', '    h1 strong { color: var(--text); }', '</style>', V_H1),
   checks=['body', 'h1', 'h1 strong'])
fx(S, 'should override style with variables(that contain spaces)', ml(
    '<style>', '    :root {', '        --bg: gray;', '        --text: red;', '    }',
    '    h1 { background: var( --bg ); }', '    h1 strong { color: var( --text ); }', '</style>', V_H1),
   checks=['body', 'h1', 'h1 strong'])
fx(S, 'should override style with variables (reverse order)', ml(
    '<style>', '    h1 { background: var(--bg); }', '    h1 strong { color: var(--text); }', '</style>',
    '<style>', '    :root {', '        --bg: gray;', '        --text: green;', '    }', '</style>', V_H1),
   checks=['body', 'h1', 'h1 strong'])
fx(S, 'should skip undefined variables', ml(
    '<style>', '    h1 { background: var(--bg); }', '    h1 strong { color: var(--text); }', '</style>', V_H1),
   checks=['body', 'h1', 'h1 strong'])
fx(S, 'should use fallback variable value', ml(
    '<style>', '    h1 { color: var(--text, red); }', '</style>', V_H1), checks=['h1'])
fx(S, 'should not use fallback variable value', ml(
    '<style>', '    :root {', '        --text: green;', '    }', '    h1 { color: var(--text, red); }',
    '</style>', V_H1), checks=['h1'])
fx(S, 'should handle variables referencing other variables', ml(
    '<style>', '    :root {', '        --alert: red;', '        --text: var(--alert);', '    }',
    '    h1 { color: var(--text); }', '</style>', V_H1), checks=['h1'])
fx(S, 'should handle variables referencing other variables (reverse order)', ml(
    '<style>', '    :root {', '        --text: var(--alert);', '        --alert: red;', '    }',
    '    h1 { color: var(--text); }', '</style>', V_H1), checks=['h1'])
fx(S, 'should handle shorthand background with deep color refs', ml(
    '<style>', '    :root {', '        --red: red;', '        --bg: var(--red);', '    }',
    '    h1 {', '        background: var(--bg);', '    }', '</style>',
    '<h1>CSS <strong>variables</strong></h1>'), checks=['h1'])
fx(S, 'should handle background with deep color refs (backwards)', ml(
    '<style>', '    h1 {', '        background: var(--bg);', '    }', '    :root {',
    '        --red: red;', '        --bg: var(--red);', '    }', '</style>',
    '<h1>CSS <strong>variables</strong></h1>'), checks=['h1'])
fx(S, 'should update background variable when it resolves later', ml(
    '<style>', '    h1 {', '        background: var(--bg, white);', '    }', '</style>',
    '<h1>Background with lately defined variable</h1>'),
   script=A("const style = document.createElement('style');",
            "style.textContent = ':root { --bg: red; }';", 'document.body.append(style);', wait(0)),
   checks=['h1'])
fx(S, 'should handle multi-type vars with deep color refs', ml(
    '<style>', '    h1 {', '        background: var(--bg);', '        color: var(--red);', '    }',
    '    :root {', '        --red: red;', '        --bg: var(--red);', '    }', '</style>',
    '<h1>CSS <strong>variables</strong></h1>'), checks=['h1'])
_depth = 30
_vl = ['        --x%d: var(--x%d) var(--x%d);' % (i, i + 1, i + 1) for i in range(1, _depth)]
_vl.append('        --x%d: #770000;' % _depth)
fx(S, 'should not hang on exponentially expanding variable references', ml(
    '<style>', '    :root {', *_vl, '    }', '    h1 {', '        color: rgb(var(--x1), 0, 0);', '    }',
    '</style>', '<h1>CSS <strong>variables</strong></h1>'), checks=['h1'])
fx(S, 'should handle variables having multiple types', ml(
    '<style>', '    :root {', '        --dark: red;', '        --light: green;', '    }',
    '    .dark {', '        background-color: var(--dark);', '        color: var(--light);', '    }',
    '    .light {', '        background: var(--light);', '        color: var(--dark);', '    }', '</style>',
    '<h1 class="dark">Dark background light text</h1>',
    '<h1 class="light">Light background dark text</h1>'), checks=['.dark', '.light'])
# (a commented-out test, "variables having multiple types in shorthand properties", is not
# part of the suite and is therefore not included)
fx(S, 'should use fallback when nested variables are missing', ml(
    '<style>', '    h1 { color: var(--text, var(--alert, green)); }', '</style>', V_H1), checks=['h1'])
fx(S, 'should not freeze on cyclic references', ml(
    '<style>', '    :root {', '        --text: var(--text);', '    }', '    h1 { color: var(--text); }',
    '</style>', V_H1), checks=['h1'])
fx(S, 'should not freeze on nested cyclic references', ml(
    '<style>', '    :root {', '        --alert: var(--text);', '        --text: var(--alert);', '    }',
    '    h1 { color: var(--text); }', '</style>', V_H1), checks=['h1'])
fx(S, 'should react on variable change', ml(
    '<style id="variables">', '    :root {', '        --text: red;', '    }', '</style>',
    '<style>', '    h1 { color: var(--text); }', '</style>', V_H1),
   script=A("document.getElementById('variables').textContent = ':root { --text: green; }';", wait(0)),
   checks=['h1'])
fx(S, 'should use <html> element variables', ml(
    '<style>', '    h1 { color: var(--text); }', '</style>', V_H1),
   pre_script="document.documentElement.setAttribute('style', '--text: red;');",
   script=A("document.documentElement.setAttribute('style', '--text: green;');", wait(0)),
   checks=['h1'], slug_override='should-use-html-element-variables')
fx(S, 'should consider variable selector', ml(
    '<style>', '    .red {', '        --text: red;', '    }', '    .green {', '        --text: green;',
    '    }', '    h1 { color: var(--text); }', '</style>',
    '<h1 class="red">Red CSS variable</h1>', '<h1 class="green">Green CSS variable</h1>'),
   checks=['.red', '.green'])
fx(S, 'should handle internal conversion of hex to RGB', ml(
    '<style>', '   :root {', '       --bg: #fff;', '       --text: #000;', '   }', '</style>',
    '<style>', '   h1 {', '       background: var(--bg);', '       color: var(--text);', '   }', '</style>',
    '<h1>Dark <strong>Theme</strong>!</h1>'), checks=['h1'])
fx(S, 'should handle variables inside color values (constructed colors)', ml(
    '<style>', '    :root {', '        --bg: 255, 255, 255;', '        --text: 0, 0, 0;', '    }', '</style>',
    '<style>', '    h1 {', '        background: rgb(var(--bg));', '        color: rgb(var(--text));', '    }',
    '</style>', '<h1>Colors with variables inside</h1>'), checks=['h1'])
fx(S, 'should use fallback when variable inside a color not found', ml(
    '<style>', '    h1 {', '        background: rgb(var(--bg, 255, 0, 0));', '    }', '</style>',
    '<h1>Colors with variables inside</h1>'), checks=['h1'])
fx(S, 'should inspect fallback when variable is undefined', ml(
    '<style>', '    h1 {', '        --bg: var(--undefined-var, red);', '        background: var(--bg);',
    '    }', '</style>', '<h1>Colors with variables inside</h1>'), checks=['h1'])
fx(S, 'should handle variables in constructed colors that refer to other vars', ml(
    '<style>', '    :root {', '        --v255: 255;', '        --red: var(--v255), 0, 0;',
    '        --bg: var(--unknown, var(--red));', '        --text: var(--red);', '    }', '</style>',
    '<style>', '    h1 {', '        background: rgb(var(--bg));', '        color: rgb(var(--text));', '    }',
    '</style>', '<h1>Colors with variables inside</h1>'), checks=['h1'])
fx(S, 'should handle variables that refer to constructed colors', ml(
    '<style>', '    :root {', '        --red: 255, 0, 0;', '        --blue: 0, 0, 255;',
    '        --rgb-blue: rgb(var(--blue));', '        --bg: rgb(var(--red));',
    '        --text: var(--rgb-blue);', '    }', '</style>',
    '<style>', '    h1 {', '        background: var(--bg);', '        color: var(--text);', '    }', '</style>',
    '<h1>Colors with variables inside</h1>'), checks=['h1'])
fx(S, 'should handle variables that refer to constructed colors asynchronously', ml(
    '<style>', '    :root {', '        --red: 255, 0, 0;', '        --bg: rgb(var(--red));', '    }',
    '    h1 {', '        color: var(--text);', '    }', '</style>',
    '<h1>Colors with variables inside</h1>'),
   script=A("const anotherStyle = document.createElement('style');",
            'anotherStyle.textContent = ' + repr(ml(
                ':root {', '    --blue: 0, 0, 255;', '    --rgb-blue: rgb(var(--blue));',
                '    --text: var(--rgb-blue);', '}', 'h1 {', '    background: var(--bg);', '}')).replace('\\n', '\\n') + ';',
            'document.body.append(anotherStyle);', wait(0)), checks=['h1'])
fx(S, 'should handle variables that are both contructed and usual colors', ml(
    '<style>', '    :root {', '        --red: 255, 0, 0;', '        --bg: green;', '    }',
    '    h1 {', '        --bg: rgb(var(--red));', '        background: var(--bg)', '    }', '</style>',
    '<h1>Colors with variables inside</h1>'), checks=['h1'])
fx(S, 'should handle cyclic references in constructed colors', ml(
    '<style>', '    :root {', '        --bg: var(--text);', '        --text: var(--bg);', '    }', '</style>',
    '<style>', '    h1 {', '        background: rgb(var(--bg));', '        color: rgb(var(--text));', '    }',
    '</style>', '<h1>Colors with variables inside</h1>'), checks=['h1'])
fx(S, 'should handle variables inside border color values', ml(
    '<style>', '    :root {', '        --red: 255, 0, 0;', '    }', '</style>',
    '<style>', '    h1 {', '        border: 1px solid rgb(var(--red));', '    }', '</style>',
    '<h1>Colors with variables inside</h1>'), checks=['h1'])
fx(S, 'should handle media variables', ml(
    '<style>', '    @media screen and (min-width: 2px) {', '        .red {', '            --text: red;',
    '        }', '        .orange {', '            --text: orange', '        }', '    }',
    '    @media screen and (min-width: 2000000px) {', '        .green {', '            --text: green;',
    '        }', '    }', '    h1 { color: var(--text); }', '</style>',
    '<h1 class="red">Red CSS variable</h1>', '<h1 class="green">Green CSS variable</h1>',
    '<h1 class="orange">Orange CSS variable</h1>'), checks=['body', '.red', '.green', '.orange'])
fx(S, 'should handle nested variables', ml(
    '<style>',
    '    @media screen and (min-width: 2px) {', '        @media screen and (min-width: 3px) {',
    '            .red {', '                --text: red;', '            }', '        }', '    }',
    '    @media screen and (min-width: 2px) {', '        @media screen and (min-width: 2000000px) {',
    '            .green {', '                --text: green;', '            }', '        }', '    }',
    '    @media screen and (min-width: 2000000px) {', '        @media screen and (min-width: 2px) {',
    '            .orange {', '                --text: orange;', '            }', '        }', '    }',
    '    h1 {', '        color: var(--text);', '    }', '</style>',
    '<h1 class="red">Red CSS variable</h1>', '<h1 class="green">Green CSS variable</h1>',
    '<h1 class="orange">Orange CSS variable</h1>'), checks=['body', '.red', '.green', '.orange'])
fx(S, 'should handle media with the same selectors', ml(
    '<style>', '    @media screen and (min-width: 2px) {', '        h1 {', '            --text: green;',
    '        }', '    }', '    @media screen and (max-width: 2px) {', '        h1 {',
    '            --text: red;', '        }', '    }', '    h1 { color: var(--text); }', '</style>',
    '<h1>Media with same selectors</h1>'), checks=['h1'])
fx(S, 'should preserve media after change', ml(
    '<style>', '    @media screen and (min-width: 2px) {', '        /* This media should be used */',
    '        h1 {', '            --text: green;', '        }', '    }',
    '    @media screen and (max-width: 2px) {', '        /* This media should not be used */',
    '        h1 {', '            --text: red;', '        }', '    }', '    h1 { color: var(--text); }',
    '</style>', '<h1>Media after change</h1>'), checks=['h1'])
# (the original calls createOrUpdateDynamicTheme a second time; only the first start is reproducible)
fx(S, 'should handle same selector with different variables', ml(
    '<style>', '    @media screen and (min-width: 2px) {', '        h1 {', '            --text: green;',
    '        }', '        h1 {', '            --bg: red;', '        }', '    }',
    '    h1 { color: var(--text); background-color: var(--bg); }', '</style>',
    '<h1>Media with same selectors</h1>'), checks=['h1'])
fx(S, 'should properly modify variables in light mode', ml(
    '<style>', '    :root {', '        --bg: white;', '        --text: black;', '    }', '    h1 {',
    '        background: var(--bg);', '        color: var(--text);', '    }', '</style>',
    '<h1>Light scheme</h1>'), checks=['h1'], theme_specific=True)
fx(S, 'should handle variables inside values', ml(
    '<style>', '    :root {', '        --border-color: #ff0000;', '        --text: green;', '    }',
    '    h1 {', '        border-bottom: 2px solid var(--border-color);', '        color: var(--text);',
    '    }', '</style>', '<h1>Border with variable</h1>'), checks=['h1'])
fx(S, 'should handle variables that have variables inside', ml(
    '<style>', '    :root {', '        --dark-red: #ff0000;', '        --border: 2px solid var(--dark-red);',
    '        --text: green;', '    }', '    h1 {', '        border: var(--border);',
    '        color: var(--text);', '    }', '</style>', '<h1>Border with variable</h1>'), checks=['h1'])
fx(S, 'should handle border color variables', ml(
    '<style>', '    :root {', '        --border-color: green;', '    }', '    h1 {',
    '        border: 1px solid;', '        border-color: var(--border-color);', '    }', '</style>',
    '<h1>Border color with variable</h1>'), checks=['h1'])
fx(S, 'should handle variables with gradients', ml(
    '<style>', '    :root {', '        --text: red;', '        --gradient: linear-gradient(red, white);',
    '        --bg: green;', '    }', '    h1 {', '        color: var(--text);',
    '        background-color: var(--bg);', '        background-image: var(--gradient);', '    }',
    '    h2 {', '        background: var(--gradient);', '    }', '</style>',
    '<h1>Weow Gradients</h1>', '<h2>Gradient 2</h2>'), checks=['h1', 'h2'])
_dark = ml('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8" width="8" height="8">',
           '    <circle fill="black" cx="4" cy="4" r="3" />', '</svg>')
_cross = ml('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8" width="8" height="8">',
            '    <path fill="red" d="M3,1 h2 v2 h2 v2 h-2 v2 h-2 v-2 h-2 v-2 h2 z" />', '</svg>')
fx(S, 'should handle variables with background images', ml(
    '<style>', '    :root {', '        --icon: url("%s");' % svg_url(_dark),
    '        --red-cross: url("%s");' % svg_url(_cross), '        --bg: green;', '    }',
    '    .icon1 {', '        background-color: var(--bg);', '        background-image: var(--icon);',
    '        background-repeat: no-repeat;', '        background-size: 100%;',
    '        display: inline-block;', '        height: 1rem;', '        width: 1rem;', '    }',
    '    .icon2 {', '        background: no-repeat center/100% var(--icon);',
    '        display: inline-block;', '        height: 1rem;', '        width: 1rem;', '    }',
    '    .icon3 {',
    '        background: no-repeat center/100% var(--red-cross), no-repeat center/100% var(--icon);',
    '        display: inline-block;', '        height: 1rem;', '        width: 1rem;', '    }', '</style>',
    '<h1>', '    <i class="icon1"></i>', '    <i class="icon2"></i>', '    <i class="icon3"></i>',
    '    Icons', '</h1>'), checks=['.icon1', '.icon2', '.icon3'])
fx(S, 'should handle variables with gradients and images', ml(
    '<style>', '    :root {', '        --icon: url("%s");' % svg_url(_dark),
    '        --gradient: linear-gradient(red, white);', '    }', '    .icon {',
    '        background: no-repeat center/100% var(--icon), var(--gradient);',
    '        display: inline-block;', '        height: 1rem;', '        width: 1rem;', '    }', '</style>',
    '<h1><i class="icon"></i>Mixed background</h1>'), checks=['.icon'])
fx(S, 'should handle asynchronous variable type resolution', ml(
    '<style>', '    :root {', '        --color1: red;', '        --color2: green;', '    }', '</style>',
    '<h1>Asynchronous variables</h1>'),
   script=A("const anotherStyle = document.createElement('style');",
            'anotherStyle.textContent = ' + repr(ml('h1 {', '    background: var(--color2);',
                                                    '    color: var(--color1);', '}')) + ';',
            'document.body.append(anotherStyle);', wait(0)), checks=['h1'])
fx(S, 'should handle async resolution of multiple variable types', ml(
    '<style>', '    :root {', '        --color: green;', '    }', '</style>',
    '<h1>Asynchronous variables with multiple types</h1>'),
   script=A("const anotherStyle = document.createElement('style');",
            'anotherStyle.textContent = ' + repr(ml('h1 {', '    background: var(--color);',
                                                    '    border: 1px solid var(--color);',
                                                    '    color: var(--color);', '}')) + ';',
            'document.body.append(anotherStyle);', wait(0)), checks=['h1'])
fx(S, 'should handle variable type resolution when style changed', ml(
    '<style>', '    :root {', '        --color1: yellow;', '        --color2: blue;', '    }', '</style>',
    '<h1>Asynchronous variables</h1>'),
   script=A("const styleEl = document.body.querySelector('style');",
            'styleEl.textContent = ' + repr(ml(':root {', '    --color1: red;', '    --color2: green;',
                                               '    --color3: blue;', '}')) + ';', wait(0),
            "const anotherStyle = document.createElement('style');",
            'anotherStyle.textContent = ' + repr(ml('h1 {', '    background: var(--color2);',
                                                    '    color: var(--color1);', '}')) + ';',
            'document.body.append(anotherStyle);', wait(0)), checks=['h1'])
fx(S, 'should handle variable type change', ml(
    '<style>', '    :root {', '        --color: green;', '    }', '    h1 {',
    '        background: var(--color);', '    }', '</style>', '<h1>Asynchronous variables</h1>'),
   script=A("const anotherStyle = document.createElement('style');",
            'anotherStyle.textContent = ' + repr(ml('h1 {', '    color: var(--color);', '}')) + ';',
            'document.body.append(anotherStyle);', wait(0)), checks=['h1'])
fx(S, 'should rebuild dependant variable rule when type becomes known', ml(
    '<style>', '    h1 {', '        background: var(--color);', '    }', '</style>',
    '<h1>Asynchronous variables</h1>'),
   script=A("const anotherStyle = document.createElement('style');",
            'anotherStyle.textContent = ' + repr(ml(':root {', '    --color: green;', '}')) + ';',
            'document.body.append(anotherStyle);', wait(50)), checks=['h1'])
fx(S, 'should not affect other declarations when variable type resolved', ml(
    '<style>', '    :root {', '        --color1: red;', '        --color2: green;', '    }', '</style>',
    '<h1 class="color1">Variables with color 1</h1>', '<h1 class="color2">Variables with color 2</h1>'),
   script=A("const anotherStyle = document.createElement('style');",
            'anotherStyle.textContent = ' + repr(ml(
                '.color1 {', '    background: var(--color1);', '    color: var(--color1);', '}',
                '.color2 {', '    background: var(--color2);', '    color: var(--color2);', '}')) + ';',
            'document.body.append(anotherStyle);', wait(0)), checks=['.color1', '.color2'])
fx(S, 'should not affect other declarations when variable type resolved', ml(
    '<style>', '    h1 {', '        --color-bg: red;', '        border: green;', '    }', '    h1 {',
    '        --color-text: green;', '    }', '</style>',
    '<h1>Variables along with other declarations</h1>'),
   script=A("const anotherStyle = document.createElement('style');",
            'anotherStyle.textContent = ' + repr(ml('h1 {', '    background-color: var(--color-bg);',
                                                    '    color: var(--color-text);', '}')) + ';',
            'document.body.append(anotherStyle);', wait(0)), checks=['h1'],
   slug_override='should-not-affect-other-declarations-when-variable-type-resolved-b')
fx(S, 'should not affect other declarations when dependency variable type resolved', ml(
    '<style>', '    h1 {', '        background: var(--color);', '        border: green;', '    }',
    '    h1 {', '        color: red;', '    }', '</style>', '<h1>Dependency variable</h1>'),
   script=A("const anotherStyle = document.createElement('style');",
            'anotherStyle.textContent = ' + repr(ml(':root {', '    --color: green;', '}')) + ';',
            'document.body.append(anotherStyle);', wait(50)), checks=['h1'])
fx(S, 'should add variables to root after the variable type is discovered', ml(
    '<style class="testcase-sheet">', '</style>', '<h1>Dependency variable</h1>'),
   pre_script="document.documentElement.setAttribute('style', '--text: red;');",
   script=A("document.querySelector('.testcase-sheet').sheet.insertRule('h1 { color: var(--text);');", wait(0)),
   checks=['h1'])
fx(S, 'should modify the caret-color property', ml(
    '<style>', '    * {', '        --caret-color: green;', '    }', '    h1 {',
    '        caret-color: var(--caret-color);', '    }', '</style>', '<h1>Caret Color</h1>'),
   checks=['h1'])
fx(S, 'should modify the box-shadow actual color values in a variable', ml(
    '<style>', '    h1 {', '        --offset: 8px;', '    }', '    h1 {',
    '        box-shadow: calc(var(--offset)*-1 - 1px) 0 0 0 #fff', '    }', '</style>',
    '<h1>COmplicated shit :(</h1>'), checks=['h1'])
fx(S, "shouldn't modify the raw value of box-shadow when their is no color", ml(
    '<style>', '    h1 {', '        --color-border-muted: green;', '    }', '    h1 {',
    '        box-shadow: inset 0 -1px 0 var(--color-border-muted)', '    }', '</style>',
    '<h1>COmplicated shit :(</h1>'), checks=['h1'],
   slug_override='shouldnt-modify-the-raw-value-of-box-shadow-when-their-is-no-color')
fx(S, 'should handle raw values within variable declarations and use proper replacement', ml(
    '<style>', '    h1 {', '        border: 1px solid rgba(var(--color,240,240,240),1);', '    }',
    '    :root {', '        --color: 123,123,123 !important;', '    }', '    div {',
    '        --color: 0,0,0 !important;', '    }', '</style>', '<h1>Raw values are spooky</h1>'),
   checks=['h1'])
fx(S, 'should modify inline variable', ml(
    '<style>', '    h1 {', '        background-color: var(--inline-var);', '    }', '</style>',
    '<h1 style="--inline-var: red">Raw values are spooky</h1>'), checks=['h1'])
fx(S, 'should preserve empty custom property that overrides non-empty', ml(
    '<style>', '    .non-empty { --grow: 1; }', '    .empty { --grow: ; }', '</style>',
    '<div class="non-empty empty">Custom property with empty values</div>'), checks=['.empty'])
fx(S, 'should not override variable inside nested @media', ml(
    '<style>', '    :root { --size: 16px; }', '    .nested-media {', '        --margin: 8px;',
    '        @media (min-width: 1px) {', '            --margin: calc(2 * var(--size));', '        }',
    '    }', '    span { display: block; margin-left: var(--margin); }', '</style>',
    '<div class="nested-media"><span>Nested media node with variables</span></div>'), checks=['span'])


if __name__ == '__main__':
    from collections import Counter
    tot = Counter(f['id'].split('/')[0] for f in FIXTURES)
    sk = Counter(f['id'].split('/')[0] for f in FIXTURES if f.get('skip'))
    ids = [f['id'] for f in FIXTURES]
    print('fixtures:', len(FIXTURES), 'skipped:', sum(sk.values()), 'unique ids:', len(ids) == len(set(ids)))
    for k in tot:
        print(' ', k, tot[k], 'skipped', sk[k])
