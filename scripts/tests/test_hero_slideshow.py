"""Regression tests for the home-page background photographs."""
import hashlib
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
HASHES = [
    '99cd6be7fc893dcbff422c11e34d011823017f6b1932911aea501860b66fef29',
    'ee6551ec55a55b2a17ece23c2a9f8191d1175c771433e5c27251e7fdffc2f913',
    'c1623e1bd8efeb5dc5c1402888bce134f362d61668bd9493a2aecb901ac02f58',
    '5fa69917710f58ef552a5dd5c2fdf254dc8a13632e4b9be342668a8c8cdf942a',
    'a5964e4b5559d704c22f38f28c68dd03c0ea1841467be20299cd87b7cb917ed8',
    '2351890bf401c1f4066d413669bfad8e83682458678e6090aaff06fa7f9bf56f',
    '8d04500a427513b1f7cc5cb7b3aae2a4e018829ab003929f12ec5491aa61c0cf',
    '01b7ceaf333a501ea3d99acb550ebd99f338c9a67a84a2f8cf87e3e192b744e4',
    'f4a232facbc5297a5556a1b1a947d3ac8ad9a99608ae675addc48edc81a591e1',
    'f1cf0c8d9aa8c5b304f1e7f0ca2876f1285b39d1eef7daf36283951698d983c7',
]

class HeroImagesTest(unittest.TestCase):
    def test_each_photo_retains_required_position(self):
        photos = yaml.safe_load((ROOT / '_data/hero.yml').read_text())
        self.assertEqual(len(photos), 10)
        for photo in photos:
            self.assertIsInstance(photo.get('position'), str, photo['file'])
            self.assertTrue(photo['position'].strip(), photo['file'])

    def test_ten_supplied_images_are_available_in_order_unchanged(self):
        photos = yaml.safe_load((ROOT / '_data/hero.yml').read_text())
        self.assertEqual([p['file'] for p in photos],
                         [f'heather-eidson-meetup-{i:02}.jpg' for i in range(1, 11)])
        for photo, digest in zip(photos, HASHES):
            data = (ROOT / 'assets/img/hero' / photo['file']).read_bytes()
            self.assertLessEqual(len(data), 500000)
            self.assertLessEqual(photo['width'], 1600)
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)

class HeroIntegrationTest(unittest.TestCase):
    def test_bilingual_home_has_background_fallback_and_existing_controls(self):
        markup = (ROOT / '_includes/pages/home.html').read_text()
        self.assertIn('data-hero-slideshow', markup)
        self.assertIn('data-hero-slide', markup)
        self.assertIn('data-hero-pause', markup)
        self.assertIn('for photo in site.data.hero', markup)
        self.assertIn('fetchpriority="high"', markup)
        self.assertIn('alt=""', markup)  # decorative, not announced repeatedly
        self.assertIn('class="hm-event"', markup)
        self.assertIn('data-signature-count', markup)
        self.assertIn('h.hero.options_btn', markup)
        self.assertNotIn('<figure class="hm-photo">', markup)
        for lang, credit in [('en', 'Photos by Heather Eidson'), ('es', 'Fotos de Heather Eidson')]:
            i18n = yaml.safe_load((ROOT / f'_data/i18n/{lang}.yml').read_text())
            self.assertEqual(i18n['home']['photo_credit'], credit)
        layout = (ROOT / '_layouts/default.html').read_text()
        self.assertIn("page.url == '/' or page.url == '/es/'", layout)
        self.assertIn('assets/css/release-home.css', layout)
        self.assertIn('release-home', layout)
        for page in ['index.html', 'es/index.html']:
            self.assertIn('hero-slideshow.js', (ROOT / page).read_text())
        self.assertTrue((ROOT / 'assets/css/release-home.css').exists())

class HeroBehaviorTest(unittest.TestCase):
    def test_photo_positions_drive_computed_crops_for_each_slide(self):
        from playwright.sync_api import sync_playwright
        import re
        markup = (ROOT / '_includes/pages/home.html').read_text()
        self.assertRegex(markup, r"assign\s+position\s*=\s*photo\.position\s*\|\s*split:")
        match = re.search(r'<img class="hm-hero__slide"[^>]*>', markup)
        assert match is not None
        tag = match.group()
        self.assertIn('data-hero-position-x="{{ position[0] | escape }}"', tag)
        self.assertIn('data-hero-position-y="{{ position[1] | escape }}"', tag)
        photos = yaml.safe_load((ROOT / '_data/hero.yml').read_text())
        self.assertEqual(len(photos), 10)
        positions = ([photo['position'] for photo in photos] + ['25% 75%', '87% 13%', '0% 100%']
                     + [f'{n}% {100 - n}%' for n in range(101)])
        for position in positions:
            self.assertRegex(position, r'^(?:100|[1-9]?[0-9])% (?:100|[1-9]?[0-9])%$')
        styles = (ROOT / 'assets/css/release-home.css').read_text()
        images = ''.join(f'<img class="hm-hero__slide" data-hero-position-x="{x}" data-hero-position-y="{y}">'
                         for x, y in (position.split() for position in positions))
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(f'<style>{styles}</style><body class="release-home">{images}</body>')
            actual = page.locator('.hm-hero__slide').evaluate_all('(images) => images.map(image => getComputedStyle(image).objectPosition)')
            self.assertEqual(actual, positions)
            browser.close()

    def test_credit_and_pause_do_not_overlap_in_both_languages(self):
        from playwright.sync_api import sync_playwright
        import re
        styles = '\n'.join((ROOT / 'assets/css' / name).read_text()
                           for name in ('main.css', 'home.css', 'release-home.css'))
        markup = (ROOT / '_includes/pages/home.html').read_text()
        credit = re.search(r'<p class="hm-hero__credit".*?</p>', markup).group()
        button = re.search(r'<button class="hm-hero__pause".*?</button>', markup).group()
        script = (ROOT / 'assets/js/hero-slideshow.js').read_text()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for lang, width in [(lang, width) for lang in ('en', 'es') for width in (320, 390, 1440)]:
                with self.subTest(lang=lang, width=width):
                    text = yaml.safe_load((ROOT / f'_data/i18n/{lang}.yml').read_text())['home']['photo_credit']
                    render_button = re.sub(r"{% if page.lang == 'es' %}(.*?){% else %}(.*?){% endif %}",
                                           lambda m: m.group(1 if lang == 'es' else 2), button)
                    html = f'''<style>{styles}</style><body class="release-home"><div class="hm">
                      <section class="hm-hero" data-hero-slideshow>
                        <div class="hm-hero__background"><img class="hm-hero__slide" data-hero-slide data-active="true"><img class="hm-hero__slide" data-hero-slide></div>
                        {credit.replace('{{ h.photo_credit }}', text)}{render_button}
                        <div class="hm-wrap hm-hero__inner"><div class="hm-hero__copy">Copy</div><div class="hm-hero__media">Event</div></div>
                      </section></div></body>'''
                    page = browser.new_page(viewport={'width': width, 'height': 900}, reduced_motion='no-preference')
                    page.set_content(html)
                    page.add_script_tag(content=script)
                    for state in ('running', 'paused', 'resumed'):
                        if state != 'running':
                            page.locator('[data-hero-pause]').click()
                        expected = ('Reanudar fotos' if lang == 'es' else 'Resume photos') if state == 'paused' else ('Pausar fotos' if lang == 'es' else 'Pause photos')
                        self.assertEqual(page.locator('[data-hero-pause]').inner_text(), expected)
                        boxes = page.evaluate('''() => Object.fromEntries(['.hm-hero__credit', '.hm-hero__pause', '.hm-hero__inner', '.hm-hero'].map(s => {
                          const r = document.querySelector(s).getBoundingClientRect();
                          return [s, {left:r.left, right:r.right, top:r.top, bottom:r.bottom}];
                        }))''')
                        c, b = boxes['.hm-hero__credit'], boxes['.hm-hero__pause']
                        self.assertTrue(c['right'] <= b['left'] or b['right'] <= c['left'] or c['bottom'] <= b['top'] or b['bottom'] <= c['top'], (lang, width, state, boxes))
                        for box in (c, b):
                            self.assertGreaterEqual(box['left'], 0, boxes)
                            self.assertLessEqual(box['right'], width, boxes)
                            self.assertGreaterEqual(box['top'], boxes['.hm-hero']['top'], boxes)
                            self.assertLessEqual(box['bottom'], boxes['.hm-hero']['bottom'], boxes)
                    page.close()
            browser.close()

    def test_open_calendar_menu_stays_inside_hero_at_narrow_widths(self):
        from playwright.sync_api import sync_playwright
        styles = '\n'.join((ROOT / 'assets/css' / name).read_text()
                           for name in ('main.css', 'home.css', 'release-home.css'))
        html = f'''<style>{styles}</style><body class="release-home"><div class="hm">
          <section class="hm-hero"><div class="hm-wrap hm-hero__inner">
            <div class="hm-hero__copy"><h1 class="hm-hero__title">Our schools</h1></div>
            <div class="hm-hero__media"><aside class="hm-event">
              <h2 class="hm-event__date">Community meeting</h2>
              <p class="hm-event__times">Sunday at 1 p.m.</p>
              <p class="hm-event__place">Twiggs Park</p>
              <details class="cal-menu"><summary class="btn btn--navy btn--block">Add to calendar</summary>
                <ul class="cal-menu__list"><li><a href="#google">Google</a></li><li><a href="#apple">Apple</a></li>
                <li><a href="#outlook">Outlook</a></li><li><a href="#office">Office 365</a></li></ul>
              </details>
            </aside></div>
          </div></section></div></body>'''
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for width in (320, 390, 768):
                with self.subTest(width=width):
                    page = browser.new_page(viewport={'width': width, 'height': 900})
                    page.set_content(html)
                    page.locator('.cal-menu summary').click()
                    boxes = page.evaluate('''() => {
                      const hero = document.querySelector('.hm-hero').getBoundingClientRect();
                      const menu = document.querySelector('.cal-menu__list').getBoundingClientRect();
                      return {hero: {left: hero.left, right: hero.right, top: hero.top, bottom: hero.bottom},
                              menu: {left: menu.left, right: menu.right, top: menu.top, bottom: menu.bottom}};
                    }''')
                    self.assertGreaterEqual(boxes['menu']['top'], boxes['hero']['top'], boxes)
                    self.assertLessEqual(boxes['menu']['bottom'], boxes['hero']['bottom'], boxes)
                    self.assertGreaterEqual(boxes['menu']['left'], 0, boxes)
                    self.assertLessEqual(boxes['menu']['right'], width, boxes)
                    page.locator('.cal-menu__list a').last.click()
                    page.close()
            browser.close()

    def test_slideshow_does_not_initialize_outside_release_home(self):
        from playwright.sync_api import sync_playwright
        script = ROOT / 'assets/js/hero-slideshow.js'
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content('''<div data-hero-slideshow>
              <img data-hero-slide data-active="true"><img data-hero-slide>
              <button data-hero-pause data-pause="Pause" data-play="Play" hidden>Pause</button>
            </div>''')
            page.add_script_tag(content=script.read_text())
            self.assertTrue(page.locator('[data-hero-pause]').is_hidden())
            browser.close()

    def test_pending_image_is_cancelled_during_pause_visibility_or_reduced_motion(self):
        from playwright.sync_api import sync_playwright
        import base64
        script = (ROOT / 'assets/js/hero-slideshow.js').read_text()
        image = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=='
        html = f'''<body class="release-home"><div data-hero-slideshow>
          <img data-hero-slide data-active="true" src="{image}" alt="">
          <img data-hero-slide data-src="https://hero.test/pending.jpg" alt="">
          <img data-hero-slide data-src="{image}" alt="">
          <button data-hero-pause data-pause="Pause" data-play="Play" hidden>Pause</button>
        </div>'''
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for reason in ('pause', 'reduced-motion', 'hidden'):
                with self.subTest(reason=reason):
                    page = browser.new_page(reduced_motion='no-preference')
                    pending = []
                    page.route('https://hero.test/pending.jpg', lambda route: pending.append(route))
                    page.clock.install()
                    page.set_content(html)
                    page.add_script_tag(content=script)
                    page.clock.fast_forward(8000)
                    page.wait_for_function("document.querySelectorAll('[data-hero-slide]')[1].hasAttribute('src')")
                    page.wait_for_timeout(50)
                    self.assertEqual(len(pending), 1)
                    if reason == 'pause':
                        page.locator('[data-hero-pause]').click()
                    elif reason == 'reduced-motion':
                        page.emulate_media(reduced_motion='reduce')
                    else:
                        page.evaluate("Object.defineProperty(document, 'hidden', {configurable:true, value:true}); document.dispatchEvent(new Event('visibilitychange'))")
                    pending[0].fulfill(status=200, content_type='image/gif', body=base64.b64decode(image.split(',')[1]))
                    page.wait_for_function("document.querySelectorAll('[data-hero-slide]')[1].naturalWidth > 0")
                    page.clock.fast_forward(20000)
                    self.assertEqual(page.locator('[data-hero-slide]').nth(0).get_attribute('data-active'), 'true')
                    if reason == 'pause':
                        page.locator('[data-hero-pause]').click()
                    elif reason == 'reduced-motion':
                        page.emulate_media(reduced_motion='no-preference')
                    else:
                        page.evaluate("Object.defineProperty(document, 'hidden', {configurable:true, value:false}); document.dispatchEvent(new Event('visibilitychange'))")
                    page.clock.fast_forward(8000)
                    page.wait_for_function("document.querySelectorAll('[data-hero-slide]')[1].dataset.active === 'true'")
                    page.clock.fast_forward(8000)
                    page.wait_for_function("document.querySelectorAll('[data-hero-slide]')[2].dataset.active === 'true'")
                    page.close()
            browser.close()

    def test_pending_image_times_out_and_late_load_does_not_replace_new_slide(self):
        from playwright.sync_api import sync_playwright
        script = (ROOT / 'assets/js/hero-slideshow.js').read_text()
        image = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=='
        html = f'''<body class="release-home"><div data-hero-slideshow>
          <img data-hero-slide data-active="true" src="{image}" alt="">
          <img data-hero-slide data-src="https://hero.test/pending.jpg" alt="">
          <img data-hero-slide data-src="{image}" alt="">
          <button data-hero-pause data-pause="Pause" data-play="Play" hidden>Pause</button>
        </div>'''
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(reduced_motion='no-preference')
            pending = []
            page.route('https://hero.test/pending.jpg', lambda route: pending.append(route))
            page.clock.install()
            page.set_content(html)
            page.add_script_tag(content=script)
            slides = page.locator('[data-hero-slide]')
            page.clock.fast_forward(8000)
            page.wait_for_function("document.querySelectorAll('[data-hero-slide]')[1].hasAttribute('src')")
            page.clock.run_for(16000)
            page.wait_for_function("document.querySelectorAll('[data-hero-slide]')[2].dataset.active === 'true'", timeout=2000)
            page.wait_for_timeout(50)
            self.assertEqual(len(pending), 1)
            pending[0].fulfill(status=200, content_type='image/gif', body=__import__('base64').b64decode(image.split(',')[1]))
            page.wait_for_function("document.querySelectorAll('[data-hero-slide]')[1].naturalWidth > 0")
            self.assertEqual(slides.nth(2).get_attribute('data-active'), 'true')
            self.assertIsNone(slides.nth(1).get_attribute('data-active'))
            page.locator('[data-hero-pause]').click()
            page.clock.fast_forward(20000)
            self.assertEqual(slides.nth(2).get_attribute('data-active'), 'true')
            page.locator('[data-hero-pause]').click()
            page.clock.fast_forward(8000)
            page.wait_for_function("document.querySelectorAll('[data-hero-slide]')[0].dataset.active === 'true'")
            browser.close()

    def test_slideshow_skips_failed_image_on_next_interval(self):
        from playwright.sync_api import sync_playwright
        script = ROOT / 'assets/js/hero-slideshow.js'
        image = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=='
        html = f'''<body class="release-home"><div data-hero-slideshow>
          <img data-hero-slide data-active="true" src="{image}" alt="">
          <img data-hero-slide data-src="data:image/gif;base64,INVALID" alt="">
          <img data-hero-slide data-src="{image}" alt="">
          <button data-hero-pause data-pause="Pause" data-play="Play" hidden>Pause</button>
        </div>'''
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(reduced_motion='no-preference')
            page.clock.install()
            page.set_content(html)
            page.add_script_tag(content=script.read_text())
            page.clock.fast_forward(8000)
            page.wait_for_function('''() => {
              const image = document.querySelectorAll('[data-hero-slide]')[1];
              return image.hasAttribute('src') && image.complete && !image.naturalWidth;
            }''')
            self.assertEqual(page.locator('[data-hero-slide]').nth(0).get_attribute('data-active'), 'true')
            page.clock.fast_forward(8000)
            page.wait_for_function("document.querySelectorAll('[data-hero-slide]')[2].dataset.active === 'true'", timeout=2000)
            browser.close()

    def test_slideshow_rotates_lazily_and_pauses_for_visibility_and_motion(self):
        script = ROOT / 'assets/js/hero-slideshow.js'
        self.assertTrue(script.exists(), 'the slideshow behavior is not implemented')
        from playwright.sync_api import sync_playwright
        image = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=='
        html = f'''<body class="release-home"><div data-hero-slideshow>
          <img data-hero-slide data-active="true" src="{image}" alt="">
          <img data-hero-slide data-src="{image}" alt="">
          <img data-hero-slide data-src="{image}" alt="">
          <button data-hero-pause data-pause="Pause" data-play="Play" hidden>Pause</button>
        </div>'''
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(reduced_motion='no-preference')
            page.clock.install()
            page.set_content(html)
            page.add_script_tag(content=script.read_text())
            slides = page.locator('[data-hero-slide]')
            self.assertIsNone(slides.nth(1).get_attribute('src'))
            page.clock.fast_forward(8000)
            page.wait_for_function("document.querySelectorAll('[data-hero-slide]')[1].dataset.active === 'true'")
            self.assertIsNone(slides.nth(2).get_attribute('src'))
            page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, value: true}); document.dispatchEvent(new Event('visibilitychange'))")
            page.clock.fast_forward(20000)
            self.assertEqual(slides.nth(1).get_attribute('data-active'), 'true')
            page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, value: false}); document.dispatchEvent(new Event('visibilitychange'))")
            page.emulate_media(reduced_motion='reduce')
            page.clock.fast_forward(20000)
            self.assertEqual(slides.nth(1).get_attribute('data-active'), 'true')
            page.emulate_media(reduced_motion='no-preference')
            page.locator('[data-hero-pause]').click()
            self.assertEqual(page.locator('[data-hero-pause]').inner_text(), 'Play')
            self.assertIsNone(page.locator('[data-hero-pause]').get_attribute('aria-pressed'))
            page.clock.fast_forward(20000)
            self.assertEqual(slides.nth(1).get_attribute('data-active'), 'true')
            page.locator('[data-hero-pause]').click()
            page.clock.fast_forward(8000)
            page.wait_for_function("document.querySelectorAll('[data-hero-slide]')[2].dataset.active === 'true'")
            browser.close()

if __name__ == '__main__':
    unittest.main()
