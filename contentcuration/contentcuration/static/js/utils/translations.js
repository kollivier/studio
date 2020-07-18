import Vue from 'vue';
var vueIntl = require("vue-intl");

var translations = window.ALL_MESSAGES || {};  // Set in django

// Flatten translation dictionary
var unnested_translations = {};
Object.keys(translations).forEach(function (key) {
    Object.keys(translations[key]).forEach(function(nestedKey) {
        unnested_translations[key + "." + nestedKey] = translations[key][nestedKey];
    });
});

Vue.use(vueIntl, {"defaultLocale": "en"});

var currentLanguage = "en";
if (global.languageCode) {
    currentLanguage = global.languageCode;
    Vue.setLocale(currentLanguage);
}

Vue.registerMessages(currentLanguage, unnested_translations);
Vue.prototype.$tr = function $tr(messageId, args) {
    const nameSpace = this.$options.name;
    if (args) {
        if (!Array.isArray(args) && typeof args !== 'object') {
            logging.error(`The $tr functions take either an array of positional
                            arguments or an object of named options.`);
        }
    }
    const defaultMessageText = this.$options.$trs[messageId];
    const message = {
        id: `${nameSpace}.${messageId}`,
        defaultMessage: defaultMessageText,
    };

    return this.$formatMessage(message, args);
};

module.exports =  translations;
