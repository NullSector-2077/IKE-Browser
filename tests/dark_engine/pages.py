"""Synthetic local pages for comparing dark modes (I.K.E. Dark Engine study).

Each page marks what the metrics check:
  data-check="keep"     must look as it does with dark mode off (a photo, a canvas)
  data-check="visible"  must stay visible against what surrounds it (icons, logos, inputs)
  data-media            an area drawn by an image (left out of the light-leftover count)
"""

import io
import random

from PIL import Image, ImageDraw

W, H = 800, 900

BASE = "<!doctype html><meta charset=utf-8><title>%s</title><style>body{font:16px/1.5 sans-serif;margin:24px}%s</style>%s"

LOREM = ("I.K.E. renders this paragraph so that its contrast can be measured. "
         "Dark mode must keep every line readable, every icon visible and every photo untouched. ")


def images():
    """name -> PNG bytes."""
    out = {}
    rnd = random.Random(7)
    # a "photo": smooth colourful gradients with a sun and some noise
    im = Image.new("RGB", (320, 200))
    px = im.load()
    for y in range(200):
        for x in range(320):
            px[x, y] = (min(255, 90 + y // 2 + rnd.randint(0, 12)), min(255, 140 + x // 6), max(0, 220 - y))
    ImageDraw.Draw(im).ellipse((220, 30, 280, 90), fill=(255, 230, 120))
    ImageDraw.Draw(im).rectangle((0, 150, 320, 200), fill=(60, 110, 40))
    out["photo.png"] = im
    # a logo: dark wordmark and mark on a transparent background
    im = Image.new("RGBA", (200, 60), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((5, 5, 55, 55), fill=(30, 30, 40, 255))
    for i in range(4):
        d.rectangle((70 + i * 30, 15, 90 + i * 30, 45), fill=(30, 30, 40, 255))
    out["logo.png"] = im
    # a white icon on a transparent background (meant for a coloured button)
    im = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(4, 12), (12, 4), (20, 12), (17, 12), (17, 20), (7, 20), (7, 12)], fill=(255, 255, 255, 255))
    out["icon-white.png"] = im
    res = {}
    for k, im in out.items():
        b = io.BytesIO()
        im.save(b, "PNG")
        res[k] = b.getvalue()
    return res


def para(n=2):
    return "".join("<p>%s</p>" % (LOREM * 2) for _ in range(n))


PAGES = {
    "01-white": BASE % ("white", "body{background:#fff;color:#222}a{color:#0645ad}",
                        "<h1>Plain white page</h1>" + para(3) + '<p><a href="#">A link in the text</a></p>'),
    "02-grey-blue": BASE % ("grey", "body{background:#c8c8c8;color:#333}"
                            ".panel{background:#d6eaff;color:#003366;padding:12px;border:1px solid #9cc3ef}",
                            "<h1>Mid-grey page</h1>" + para(1) + '<div class=panel><b>Light-blue panel</b>' + para(1)
                            + "</div>"),
    "03-logo": BASE % ("logo", "body{background:#fff;color:#222}header{padding:8px;border-bottom:1px solid #ddd}",
                       '<header><img data-check=visible src="/img/logo.png" width=200 height=60 alt=""></header>'
                       + para(2)),
    "04-icon-white": BASE % ("icon", "body{background:#fff;color:#222}"
                             ".btn{display:inline-block;background:#1a73e8;padding:8px;border-radius:4px;margin:4px}"
                             ".dark{background:#333}",
                             "<h1>Icons</h1>" + '<span class=btn><img data-check=visible src="/img/icon-white.png" '
                             'width=24 height=24></span><span class="btn dark"><img data-check=visible '
                             'src="/img/icon-white.png" width=24 height=24></span>' + para(1)),
    "05-svg": BASE % ("svg", "body{background:#fff;color:#333}.ic{width:32px;height:32px}",
                      '<h1>Inline SVG</h1><p><svg data-check=visible class=ic viewBox="0 0 24 24">'
                      '<path fill="#333" d="M3 12l9-9 9 9h-3v9H6v-9z"/></svg> '
                      '<svg data-check=visible class=ic viewBox="0 0 24 24" fill="currentColor">'
                      '<circle cx=12 cy=12 r=9 /></svg></p>' + para(2)),
    "06-photo": BASE % ("photo", "body{background:#fff;color:#222}figure{margin:0}",
                        '<h1>Photo</h1><figure><img data-check=keep src="/img/photo.png" width=320 height=200>'
                        "<figcaption>A caption under the photo</figcaption></figure>" + para(1)),
    "07-canvas": BASE % ("canvas", "body{background:#fff;color:#222}",
                         '<h1>Canvas</h1><canvas data-check=keep id=c width=300 height=150></canvas>' + para(1)
                         + "<script>var x=document.getElementById('c').getContext('2d');x.fillStyle='#fff';"
                         "x.fillRect(0,0,300,150);x.fillStyle='#d33';x.fillRect(20,20,80,80);x.fillStyle='#000';"
                         "x.font='20px sans-serif';x.fillText('chart',140,80);</script>"),
    "08-table": BASE % ("table", "body{background:#fff;color:#222}table{border-collapse:collapse;width:100%}"
                        "td,th{border:1px solid #ddd;padding:6px}th{background:#4a4a4a;color:#fff}"
                        "tr:nth-child(even) td{background:#f2f2f2}",
                        "<h1>Zebra table</h1><table><tr><th>Name</th><th>Value</th></tr>"
                        + "".join("<tr><td>Row %d</td><td>%d euro</td></tr>" % (i, i * 7) for i in range(12))
                        + "</table>"),
    "09-form": BASE % ("form", "body{background:#fff;color:#222}label{display:block;margin-top:10px}"
                       ".primary{background:#007bff;color:#fff;border:0;padding:8px 16px;border-radius:4px}"
                       "input,select,textarea{font:inherit}",
                       "<h1>Form</h1><form><label>Name <input data-check=visible placeholder='Your name'></label>"
                       "<label>Mail <input data-check=visible type=email value='a@example.org'></label>"
                       "<label>Pick <select data-check=visible><option>One</option></select></label>"
                       "<label>Note <textarea data-check=visible rows=3>Some text</textarea></label>"
                       "<p><button class=primary type=button>Send</button> <button type=button>Cancel</button></p>"
                       "</form>"),
    "10-bg-image": BASE % ("bgimage", "body{background:#fff;color:#222}"
                           ".hero{background:url(/img/photo.png) center/cover;height:240px;padding:24px;color:#fff;"
                           "text-shadow:0 1px 2px #000}",
                           '<div class=hero data-media><h1>Text over a photo</h1><p>White caption on the image</p></div>'
                           + para(1)),
    "11-own-dark": ('<!doctype html><meta charset=utf-8><meta name=color-scheme content=dark><title>own dark</title>'
                    "<style>:root{color-scheme:dark}body{font:16px/1.5 sans-serif;margin:24px;background:#121212;"
                    "color:#ddd}a{color:#8ab4f8}.card{background:#1e1e1e;padding:12px}</style>"
                    "<h1>Already dark</h1><div class=card>" + para(2) + '<a href="#">a link</a></div>'),
    "12-dynamic": BASE % ("dynamic", "body{background:#fff;color:#222}",
                          "<h1>Added later</h1>" + para(1) + "<div id=slot></div><script>setTimeout(function(){"
                          "var s=document.createElement('style');s.textContent='.late{background:#fffbe6;"
                          "border:1px solid #f0d060;color:#5a4500;padding:12px}';document.head.appendChild(s);"
                          "var d=document.createElement('div');d.className='late';d.innerHTML='<b>Notice</b> added "
                          "by a script after the load, styled by a sheet added later too.';"
                          "document.getElementById('slot').appendChild(d);"
                          "var e=document.createElement('div');e.style.cssText='background:#ffffff;color:#444;"
                          "padding:12px;margin-top:8px;border:1px solid #ccc';e.textContent='A white card with "
                          "inline style, added after the load.';document.getElementById('slot').appendChild(e);"
                          "},300)</script>"),
}

# a page for the speed proxy: builds, styles, measures and removes elements many times
BENCH = BASE % ("bench", "body{background:#fff;color:#222}.it{background:#f4f4f4;border:1px solid #ddd;"
                "color:#333;padding:2px}.it.done{background:#e6ffe6;color:#060}",
                "<div id=root></div><script>"
                "async function bench(){var root=document.getElementById('root');var t0=performance.now();"
                "for(var r=0;r<20;r++){var f=document.createDocumentFragment();"
                "for(var i=0;i<300;i++){var d=document.createElement('div');d.className='it'+(i%3?'':' done');"
                "d.style.cssText=i%5?'':'background:#fafafa;color:#111';d.textContent='item '+i;f.appendChild(d);}"
                "root.appendChild(f);root.offsetHeight;await new Promise(function(r){setTimeout(r,0)});"
                "for(var k=0;k<root.children.length;k+=2)root.children[k].classList.toggle('done');root.offsetHeight;"
                "await new Promise(function(r){setTimeout(r,0)});root.textContent='';"
                "await new Promise(function(r){setTimeout(r,0)});}"
                "return performance.now()-t0}</script>")


# calibration: swatches of background colours and of text colours, to compare how
# each mode maps a colour (the pixel at the centre of each swatch is read back)
def swatches():
    import colorsys
    cols = [colorsys.hls_to_rgb(0, v / 20, 0) for v in range(21)]
    for h in (0, 30, 60, 120, 180, 210, 240, 300):
        for s in (0.5, 1.0):
            for v in (0.2, 0.35, 0.5, 0.65, 0.8, 0.95):
                cols.append(colorsys.hls_to_rgb(h / 360, v, s))
    return ["#%02x%02x%02x" % tuple(round(c * 255) for c in rgb) for rgb in cols]


def swatch_xy(i):
    """Centre of background swatch i and of text swatch i."""
    x, y = 10 + (i % 20) * 38, 10 + (i // 20) * 34
    return (x + 15, y + 14), (x + 8, 440 + (i // 20) * 34 + 14), (x + 2, 660 + (i // 20) * 34 + 14)


def calib_page():
    parts = []
    for i, c in enumerate(swatches()):
        x, y = 10 + (i % 20) * 38, 10 + (i // 20) * 34
        parts.append('<div style="position:absolute;left:%dpx;top:%dpx;width:30px;height:28px;background:%s"></div>'
                     % (x, y, c))
        parts.append('<div style="position:absolute;left:%dpx;top:%dpx;font:28px/28px monospace;color:%s">'
                     '&#x2588;</div>' % (x, 440 + (i // 20) * 34, c))
        parts.append('<div style="position:absolute;left:%dpx;top:%dpx;width:18px;height:16px;border:6px solid %s">'
                     '</div>' % (x, 660 + (i // 20) * 34, c))
    return BASE % ("calib", "body{background:#fff;color:#222;margin:0}", "".join(parts))


EXTRA = {"calib": calib_page()}
