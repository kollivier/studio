import { mount } from '@vue/test-utils';
import CopyToken from '../CopyToken.vue';

function makeWrapper() {
  return mount(CopyToken, {
    propsData: {
      token: 'testtoken',
    },
  });
}

describe('copyToken', () => {
  let wrapper;
  beforeEach(() => {
    wrapper = makeWrapper();
  });
  it('text should be populated on load', () => {
    let token = wrapper.find({ ref: 'tokenText' });
    expect(token.element.value).toEqual('testtoken');
    expect(wrapper.vm.copyStatus === 'IDLE');
  });
  // TODO: Need to figure out a way to test if text was properly
  //        copied (document.execCommand not supported)
});
