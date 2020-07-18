var config = {
  showProcessingMessages: false,
  jax: ['input/TeX', 'input/MathML', 'output/SVG'],
  extensions: [
    'tex2jax.js',
    'mml2jax.js',
    'MathMenu.js',
    'MathZoom.js',
    'AssistiveMML.js',
    '[Contrib]/a11y/accessibility-menu.js',
  ],
  TeX: { extensions: ['AMSmath.js', 'AMSsymbols.js', 'noErrors.js', 'noUndefined.js'] },
};

var SvgGenerator = {
  svg_container: null, // filled in by Init below
  timeout: null, // store setTimout id
  mjRunning: false, // true when MathJax is processing
  index: 0,

  //  Get the preview and buffer DIV's
  Init: function() {
    this.svg_container = document.createElement('div');
    this.svg_container.id = 'mathjax_container';
    MathJax.Hub.Register.MessageHook('Math Processing Error', function(message) {
      // eslint-disable-next-line no-console
      console.error(message);
    });
  },

  //  Creates the SVG container and runs MathJax on it.
  GenerateSVG: function(text, callback) {
    if (this.mjRunning) {
      MathJax.Hub.Queue(['GenerateSVG', this, text, callback]);
    } else {
      this.mjRunning = true;
      this.svg_container = document.createElement('div');
      this.svg_container.innerHTML = text;
      MathJax.Hub.Queue(
        ['Typeset', MathJax.Hub, this.svg_container],
        ['SVGDone', this, text, callback]
      );
    }
  },

  //  Indicate that MathJax is no longer running and return the result
  SVGDone: function(text, callback) {
    var result = $(this.svg_container).find('svg')[0];
    if (result) {
      result.setAttribute('data-texstring', text);
    }
    callback(result);
    this.mjRunning = false;
  },
};

function init() {
  var head = document.getElementsByTagName('head')[0],
    script;
  script = document.createElement('script');
  script.type = 'text/x-mathjax-config';
  script[window.opera ? 'innerHTML' : 'text'] =
    'MathJax.Hub.Config(' + JSON.stringify(config) + ');';
  head.appendChild(script);
  script = document.createElement('script');
  script.type = 'text/javascript';
  script.src = 'https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.1/MathJax.js';
  script.onload = function() {
    //  Cache a callback to the GenerateSVG action
    SvgGenerator.generate = MathJax.Callback(['GenerateSVG', SvgGenerator]);
    SvgGenerator.generate.autoReset = true; // make sure it can run more than once
    SvgGenerator.Init();
  };
  head.appendChild(script);
}

function toSVG(text) {
  return new Promise(function(resolve) {
    SvgGenerator.generate(text, resolve);
  });
}

module.exports = {
  init: init,
  toSVG: toSVG,
};
