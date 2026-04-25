/** @type {import('stylelint').Config} */
export default {
  extends: ['stylelint-config-standard-scss'],
  defaultSeverity: 'warning',
  rules: {
    'selector-pseudo-element-no-unknown': [
      true,
      {
        ignorePseudoElements: ['ng-deep', 'v-deep', 'v-global', 'v-slotted', 'v-bind'],
      },
    ],
  },
};
