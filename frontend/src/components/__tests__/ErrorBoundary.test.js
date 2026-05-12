/**
 * ErrorBoundary 组件测试
 * 验证正常渲染和错误捕获行为
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, onMounted } from 'vue'
import ErrorBoundary from '../ErrorBoundary.vue'

// 正常子组件
const GoodChild = defineComponent({
  template: '<div class="child">Hello</div>',
})

// 渲染时会抛错的子组件
const BadChild = defineComponent({
  setup() {
    onMounted(() => {
      throw new Error('子组件炸了')
    })
  },
  template: '<div>BOOM</div>',
})

describe('ErrorBoundary', () => {
  it('renders slot content when no error', () => {
    const wrapper = mount(ErrorBoundary, {
      slots: { default: GoodChild },
    })
    expect(wrapper.find('.child').exists()).toBe(true)
    expect(wrapper.find('.error-boundary').exists()).toBe(false)
  })

  it('shows error UI when child throws during mount', async () => {
    // suppress console.error from onErrorCaptured
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const wrapper = mount(ErrorBoundary, {
      slots: { default: BadChild },
    })
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.error-boundary').exists()).toBe(true)
    expect(wrapper.find('.error-boundary__title').text()).toContain('页面渲染异常')
    expect(wrapper.find('.error-boundary__msg').text()).toContain('子组件炸了')

    spy.mockRestore()
  })

  it('provides refresh button that calls location.reload', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const reloadMock = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { reload: reloadMock },
      writable: true,
    })

    const wrapper = mount(ErrorBoundary, {
      slots: { default: BadChild },
    })
    await wrapper.vm.$nextTick()

    const btn = wrapper.find('.error-boundary__btn')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    expect(reloadMock).toHaveBeenCalled()

    spy.mockRestore()
  })
})
