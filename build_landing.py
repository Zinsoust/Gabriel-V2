import base64, os

with open('/tmp/cover.png', 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode('ascii')

img_data = f"data:image/png;base64,{img_b64}"

reasons = [
    ("1", "La comparaison avec les autres", "Tu regardes autour de toi et vois des amies se marier. Cette frustration nait souvent d'une comparaison qui oublie que ton chemin est unique."),
    ("2", "Le doute sur ta valeur", "Une voix interieure te chuchote que si tu n'es pas encore mariee, c'est peut-etre parce que tu ne merites pas encore l'amour."),
    ("3", "La pression de l'entourage", "Les questions repetees de ta famille ou de tes proches ajoutent un poids supplementaire a une attente deja difficile."),
    ("4", "Les blessures du passe", "D'anciennes deceptions amoureuses ou familiales peuvent colorer negativement ta vision du mariage et de toi-meme."),
    ("5", "L'incertitude face a l'avenir", "Ne pas savoir quand ni avec qui genere une anxiete qui peut envahir ton quotidien et troubler ta paix."),
    ("6", "La lutte contre la solitude", "L'attente peut faire ressentir un isolement profond, meme entouree de gens, quand le desir du mariage n'est pas comble."),
    ("7", "La tension entre desir et confiance", "Tu crois en Dieu, mais cette promesse tarde... La tension entre le desir legitime du mariage et la confiance en Son timing est reelle.")
]

reason_cards = ""
for num, title, desc in reasons:
    reason_cards += f"""      <div class="reason-card card-hover bg-white dark:bg-gray-900 rounded-xl p-5 shadow-md scroll-reveal">
        <div class="flex items-start gap-4">
          <span class="text-2xl font-bold gradient-text flex-shrink-0">{num}</span>
          <div>
            <h3 class="font-semibold text-gray-800 dark:text-gray-100 mb-2">{title}</h3>
            <p class="text-sm text-gray-500 dark:text-gray-400 leading-relaxed">{desc}</p>
          </div>
        </div>
      </div>\n"""

html = """<!DOCTYPE html>
<html lang="fr" class="scroll-smooth">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title data-gumroad-field="name">7 raisons pour lesquels tu te sens frustree d'attendre le mariage</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  darkMode: 'class',
  theme: { extend: { colors: {
    gold: { 50:'#fffbeb',100:'#fef3c7',200:'#fde68a',300:'#fcd34d',400:'#fbbf24',500:'#f59e0b',600:'#d97706',700:'#b45309',800:'#92400e',900:'#78350f' }
  }}}
}
</script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400;1,600&family=Inter:wght@300;400;500;600&display=swap');
body { font-family: 'Inter', system-ui, sans-serif; }
h1,h2,h3 { font-family: 'Playfair Display', Georgia, serif; }
.gradient-text { background: linear-gradient(135deg, #c9a880 0%, #d97706 40%, #e11d48 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.hero-bg { background: radial-gradient(ellipse at 60% 0%, rgba(253,211,77,0.15) 0%, transparent 60%), radial-gradient(ellipse at 10% 80%, rgba(225,29,72,0.1) 0%, transparent 50%), #fdfaf6; }
.dark .hero-bg { background: radial-gradient(ellipse at 60% 0%, rgba(120,53,15,0.3) 0%, transparent 60%), radial-gradient(ellipse at 10% 80%, rgba(159,18,57,0.2) 0%, transparent 50%), #0f0a06; }
.card-hover { transition: transform 0.3s ease, box-shadow 0.3s ease; }
.card-hover:hover { transform: translateY(-4px); box-shadow: 0 20px 40px rgba(0,0,0,0.12); }
.shimmer-btn { background: linear-gradient(90deg, #d97706 0%, #f59e0b 40%, #fbbf24 50%, #f59e0b 60%, #d97706 100%); background-size: 200% auto; animation: shimmer 2s linear infinite; color: white; }
.reason-card { border-left: 3px solid #d97706; }
.dark .reason-card { border-left-color: #f59e0b; }
.scroll-reveal { opacity: 0; transform: translateY(24px); transition: opacity 0.7s ease, transform 0.7s ease; }
.scroll-reveal.visible { opacity: 1; transform: translateY(0); }
.ornament { color: #d97706; }
.dark .ornament { color: #f59e0b; }
.animate-float { animation: float 6s ease-in-out infinite; }
#gr-price::-webkit-outer-spin-button, #gr-price::-webkit-inner-spin-button,
#gr-price-2::-webkit-outer-spin-button, #gr-price-2::-webkit-inner-spin-button { -webkit-appearance: none; }
#gr-price, #gr-price-2 { -moz-appearance: textfield; }
@keyframes float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-12px); } }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
</style>
</head>
<body class="hero-bg text-gray-800 dark:text-gray-100 transition-colors duration-300">

<div class="fixed top-4 right-4 z-50">
  <button id="theme-btn" class="bg-white dark:bg-gray-800 shadow-md rounded-full w-10 h-10 flex items-center justify-center border border-gray-200 dark:border-gray-700 transition-all hover:scale-110" aria-label="Basculer le theme">
    <span id="theme-icon">&#127769;</span>
  </button>
</div>

<!-- Hero -->
<section class="min-h-screen flex flex-col items-center justify-center px-4 pt-16 pb-12 relative overflow-hidden">
  <div class="absolute top-20 left-4 w-64 h-64 rounded-full opacity-20 blur-3xl pointer-events-none" style="background:#fef3c7;"></div>
  <div class="absolute bottom-10 right-4 w-80 h-80 rounded-full opacity-20 blur-3xl pointer-events-none" style="background:#ffe4e6;"></div>

  <div class="max-w-5xl w-full mx-auto flex flex-col lg:flex-row items-center gap-10 lg:gap-16">
    <div class="animate-float flex-shrink-0 relative">
      <div class="absolute inset-0 rounded-2xl opacity-30 blur-xl scale-105" style="background:linear-gradient(135deg,#fcd34d,#fb7185);"></div>
      <img src="COVER_SRC" alt="Couverture e-book 7 raisons" class="relative rounded-2xl shadow-2xl w-52 sm:w-64 lg:w-72" style="outline:4px solid rgba(253,211,77,0.4);"/>
    </div>

    <div class="text-center lg:text-left max-w-xl">
      <div class="ornament mb-3 text-xl">&#10022; &#10022; &#10022;</div>
      <p class="text-sm font-semibold tracking-widest uppercase mb-4 ornament">E-book &middot; Par Gr&acirc;ce</p>
      <h1 class="text-3xl sm:text-4xl lg:text-5xl font-bold leading-tight mb-6">
        <span class="gradient-text">7 raisons pour lesquelles tu te sens frustr&eacute;e</span><br/>
        <em class="text-gray-700 dark:text-gray-200 text-2xl sm:text-3xl not-italic" style="font-style:italic;">d&apos;attendre le mariage</em>
      </h1>
      <p class="text-base sm:text-lg text-gray-600 dark:text-gray-300 leading-relaxed mb-8">
        Tu d&eacute;sires te marier, mais l&apos;attente p&egrave;se parfois lourd. Entre les comparaisons, les doutes et la pression de l&apos;entourage&hellip; tu n&apos;es pas seule. Cet e-book t&apos;aide &agrave; comprendre tes frustrations avec <strong>clart&eacute;, sagesse et discernement</strong>.
      </p>

      <div class="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-6 border border-gray-200 dark:border-gray-700 mb-2">
        <p class="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">Choisis ton prix &middot; <span class="ornament">Paiement unique</span></p>
        <div class="relative mb-4">
          <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 font-semibold">&euro;</span>
          <input id="gr-price" type="number" min="0" step="0.01" placeholder="7.99"
            class="w-full pl-8 pr-4 py-3 rounded-xl border-2 text-gray-800 dark:text-gray-100 text-lg font-semibold transition-colors dark:bg-gray-800"
            style="border-color:#fde68a;"/>
        </div>
        <div class="flex gap-2 mb-5 flex-wrap">
          <button onclick="setPrice(0)" class="px-3 py-1.5 rounded-lg text-sm font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-yellow-50 dark:hover:bg-yellow-900 transition-colors">Gratuit</button>
          <button onclick="setPrice(7.99)" class="px-3 py-1.5 rounded-lg text-sm font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-yellow-50 dark:hover:bg-yellow-900 transition-colors">&euro;7.99</button>
          <button onclick="setPrice(12)" class="px-3 py-1.5 rounded-lg text-sm font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-yellow-50 dark:hover:bg-yellow-900 transition-colors">&euro;12</button>
          <button onclick="setPrice(20)" class="px-3 py-1.5 rounded-lg text-sm font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-yellow-50 dark:hover:bg-yellow-900 transition-colors">&euro;20 &#10024;</button>
        </div>
        <button id="gr-buy" type="button" class="shimmer-btn w-full py-4 rounded-xl font-bold text-lg tracking-wide shadow-lg hover:shadow-xl transition-all hover:scale-[1.02] active:scale-[0.98]">
          Je veux cet e-book &rarr;
        </button>
        <p class="text-center text-xs text-gray-400 mt-3">&#128218; 24 pages &middot; PDF &middot; T&eacute;l&eacute;chargement imm&eacute;diat</p>
      </div>
      <p class="text-center text-xs text-gray-400">Paiement s&eacute;curis&eacute; via Gumroad &middot; Satisfaite ou rembours&eacute;e</p>
    </div>
  </div>
</section>

<div class="text-center py-6 ornament text-3xl">&#10023;</div>

<!-- About -->
<section class="py-12 px-4">
  <div class="max-w-2xl mx-auto text-center scroll-reveal">
    <h2 class="text-2xl sm:text-3xl font-bold mb-6">L&apos;attente est une <span class="gradient-text" style="font-style:italic;">saison de formation</span></h2>
    <p class="text-base sm:text-lg text-gray-600 dark:text-gray-300 leading-relaxed">
      Avant de b&acirc;tir une alliance durable, il est essentiel de d&eacute;couvrir la femme que Dieu est en train de former en toi. Gr&acirc;ce t&apos;offre des cl&eacute;s de r&eacute;flexion pour traverser cette saison avec plus de paix et de profondeur.
    </p>
    <div class="flex justify-center gap-8 mt-8 flex-wrap">
      <div class="text-center"><div class="text-3xl font-bold gradient-text">24</div><div class="text-xs uppercase tracking-wider text-gray-500 mt-1">pages</div></div>
      <div class="w-px bg-gray-200 dark:bg-gray-700 self-stretch"></div>
      <div class="text-center"><div class="text-3xl font-bold gradient-text">7</div><div class="text-xs uppercase tracking-wider text-gray-500 mt-1">frustrations d&eacute;crypt&eacute;es</div></div>
      <div class="w-px bg-gray-200 dark:bg-gray-700 self-stretch"></div>
      <div class="text-center"><div class="text-3xl font-bold gradient-text">&infin;</div><div class="text-xs uppercase tracking-wider text-gray-500 mt-1">cl&eacute;s de r&eacute;flexion</div></div>
    </div>
  </div>
</section>

<!-- 7 Reasons -->
<section class="py-16 px-4" style="background:rgba(255,255,255,0.6);">
  <div class="max-w-4xl mx-auto">
    <div class="text-center mb-12 scroll-reveal">
      <p class="text-sm font-semibold tracking-widest uppercase mb-3 ornament">Ce que tu vas d&eacute;couvrir</p>
      <h2 class="text-2xl sm:text-3xl font-bold">Les <span class="gradient-text">7 frustrations</span> au c&oelig;ur de l&apos;attente</h2>
    </div>
    <div class="grid sm:grid-cols-2 gap-5">
REASONS_BLOCK
    </div>
  </div>
</section>

<!-- What you get -->
<section class="py-16 px-4">
  <div class="max-w-3xl mx-auto scroll-reveal">
    <div class="text-center mb-10">
      <h2 class="text-2xl sm:text-3xl font-bold">Ce que <span class="gradient-text">tu re&ccedil;ois</span></h2>
    </div>
    <div class="bg-white dark:bg-gray-900 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
      <div class="h-1" style="background:linear-gradient(90deg,#d97706,#e11d48);"></div>
      <div class="p-8 space-y-5">
        <div class="flex items-start gap-4"><span class="text-2xl">&#128196;</span><div><p class="font-semibold">E-book PDF de 24 pages</p><p class="text-sm text-gray-500 dark:text-gray-400">T&eacute;l&eacute;chargement imm&eacute;diat, lisible sur tous tes appareils</p></div></div>
        <div class="border-t border-gray-100 dark:border-gray-800 pt-5 flex items-start gap-4"><span class="text-2xl">&#128269;</span><div><p class="font-semibold">7 frustrations analys&eacute;es en profondeur</p><p class="text-sm text-gray-500 dark:text-gray-400">Comprendre l&apos;origine de ce que tu ressens pour avancer avec clart&eacute;</p></div></div>
        <div class="border-t border-gray-100 dark:border-gray-800 pt-5 flex items-start gap-4"><span class="text-2xl">&#128154;</span><div><p class="font-semibold">Des cl&eacute;s de discernement spirituel</p><p class="text-sm text-gray-500 dark:text-gray-400">Pour traverser cette saison avec sagesse et confiance en Dieu</p></div></div>
        <div class="border-t border-gray-100 dark:border-gray-800 pt-5 flex items-start gap-4"><span class="text-2xl">&#128155;</span><div><p class="font-semibold">Une parole qui te rejoint l&agrave; o&ugrave; tu es</p><p class="text-sm text-gray-500 dark:text-gray-400">&Eacute;crit avec bienveillance, sans jugement, pour les femmes qui attendent</p></div></div>
      </div>
    </div>
  </div>
</section>

<!-- Author -->
<section class="py-16 px-4" style="background:rgba(255,255,255,0.6);">
  <div class="max-w-2xl mx-auto text-center scroll-reveal">
    <div class="ornament mb-4 text-2xl">&#10022;</div>
    <h2 class="text-2xl font-bold mb-4">&Agrave; propos de <span class="gradient-text">Gr&acirc;ce</span></h2>
    <p class="text-base text-gray-600 dark:text-gray-300 leading-relaxed">
      Gr&acirc;ce accompagne les femmes qui d&eacute;sirent construire un mariage solide et une vie align&eacute;e avec leur foi. &Agrave; travers ses &eacute;crits, elle partage des r&eacute;flexions authentiques pour traverser les diff&eacute;rentes saisons de la vie avec profondeur et discernement.
    </p>
  </div>
</section>

<!-- Final CTA -->
<section class="py-20 px-4">
  <div class="max-w-xl mx-auto text-center scroll-reveal">
    <div class="ornament mb-4 text-3xl">&#10022; &#10022; &#10022;</div>
    <h2 class="text-2xl sm:text-3xl font-bold mb-4">Pr&ecirc;te &agrave; comprendre <span class="gradient-text" style="font-style:italic;">ton attente&nbsp;?</span></h2>
    <p class="text-gray-600 dark:text-gray-300 mb-8">Choisis ce que tu peux offrir. L&apos;essentiel, c&apos;est que ce message t&apos;atteigne.</p>
    <div class="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-6 border border-gray-200 dark:border-gray-700">
      <div class="relative mb-4">
        <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 font-semibold">&euro;</span>
        <input id="gr-price-2" type="number" min="0" step="0.01" placeholder="7.99"
          class="w-full pl-8 pr-4 py-3 rounded-xl border-2 text-gray-800 dark:text-gray-100 text-lg font-semibold transition-colors dark:bg-gray-800"
          style="border-color:#fde68a;"/>
      </div>
      <div class="flex gap-2 mb-5 flex-wrap justify-center">
        <button onclick="setPrice2(0)" class="px-3 py-1.5 rounded-lg text-sm font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-yellow-50 dark:hover:bg-yellow-900 transition-colors">Gratuit</button>
        <button onclick="setPrice2(7.99)" class="px-3 py-1.5 rounded-lg text-sm font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-yellow-50 dark:hover:bg-yellow-900 transition-colors">&euro;7.99</button>
        <button onclick="setPrice2(12)" class="px-3 py-1.5 rounded-lg text-sm font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-yellow-50 dark:hover:bg-yellow-900 transition-colors">&euro;12</button>
        <button onclick="setPrice2(20)" class="px-3 py-1.5 rounded-lg text-sm font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-yellow-50 dark:hover:bg-yellow-900 transition-colors">&euro;20 &#10024;</button>
      </div>
      <button id="gr-buy-2" type="button" class="shimmer-btn w-full py-4 rounded-xl font-bold text-lg tracking-wide shadow-lg hover:shadow-xl transition-all hover:scale-[1.02] active:scale-[0.98]">
        Je veux cet e-book &rarr;
      </button>
      <p class="text-center text-xs text-gray-400 mt-3">&#128218; 24 pages &middot; PDF &middot; T&eacute;l&eacute;chargement imm&eacute;diat</p>
    </div>
  </div>
</section>

<footer class="py-8 text-center text-xs text-gray-400 dark:text-gray-600 border-t border-gray-200 dark:border-gray-800">
  <p>&copy; 2025 Gr&acirc;ce &middot; <span data-gumroad-field="name">7 raisons pour lesquels tu te sens frustree d'attendre le mariage</span></p>
  <p class="mt-1">Paiement s&eacute;curis&eacute; via Gumroad</p>
</footer>

<script>
var themeBtn = document.getElementById('theme-btn');
var themeIcon = document.getElementById('theme-icon');
function updateIcon() { themeIcon.textContent = document.documentElement.classList.contains('dark') ? String.fromCodePoint(0x2600,0xFE0F) : String.fromCodePoint(0x1F319); }
themeBtn.addEventListener('click', function() { document.documentElement.classList.toggle('dark'); updateIcon(); });
if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) { document.documentElement.classList.add('dark'); updateIcon(); }

function setPrice(v) { document.getElementById('gr-price').value = v === 0 ? '0' : String(v); }
function setPrice2(v) { document.getElementById('gr-price-2').value = v === 0 ? '0' : String(v); }

function doCheckout(inputId) {
  var v = (document.getElementById(inputId).value || '').trim(), params = {};
  if (v !== '') { var n = parseFloat(v); if (!isNaN(n) && n >= 0) params.price = String(n); }
  parent.postMessage({ type: 'gumroad:checkout', params: params }, '*');
}
document.getElementById('gr-buy').addEventListener('click', function() { doCheckout('gr-price'); });
document.getElementById('gr-buy-2').addEventListener('click', function() { doCheckout('gr-price-2'); });

var observer = new IntersectionObserver(function(entries) { entries.forEach(function(e) { if (e.isIntersecting) e.target.classList.add('visible'); }); }, { threshold: 0.1 });
document.querySelectorAll('.scroll-reveal').forEach(function(el) { observer.observe(el); });
</script>
</body>
</html>"""

html = html.replace("COVER_SRC", img_data).replace("REASONS_BLOCK", reason_cards)

out_path = r'C:\Users\Bélinda Warisse\Desktop\gabriel\landing.html'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

size = os.path.getsize(out_path)
print(f"Written {size:,} bytes ({size/1024:.1f} KB)")
