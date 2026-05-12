/**
 * Router 单元测试
 * 验证路由守卫、公开页面、未认证跳转
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const store = {}
Object.defineProperty(globalThis, 'sessionStorage', {
  value: {
    getItem: vi.fn((key) => store[key] ?? null),
    setItem: vi.fn((key, val) => { store[key] = val }),
    removeItem: vi.fn((key) => { delete store[key] }),
  },
})

describe('router', () => {
  let router

  beforeEach(async () => {
    vi.resetModules()
    Object.keys(store).forEach(k => delete store[k])
    const mod = await import('./router.js')
    router = mod.default
  })

  it('defines all expected routes', () => {
    const paths = router.getRoutes().map(r => r.path)
    expect(paths).toContain('/login')
    expect(paths).toContain('/')
    expect(paths).toContain('/docs')
    expect(paths).toContain('/metrics')
    expect(paths).toContain('/feedback')
    expect(paths).toContain('/audit')
    expect(paths).toContain('/admin')
  })

  it('login route is marked public', () => {
    const loginRoute = router.getRoutes().find(r => r.path === '/login')
    expect(loginRoute.meta.public).toBe(true)
  })

  it('non-login routes are not public', () => {
    const nonPublic = router.getRoutes().filter(r => r.path !== '/login')
    nonPublic.forEach(r => {
      expect(r.meta.public).toBeFalsy()
    })
  })

  it('redirects to /login when no token and accessing protected route', async () => {
    // 无 token
    delete store.rag_token

    // 模拟导航到受保护页面
    router.push('/')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('allows access to protected route when token exists', async () => {
    // 使用格式正确的 JWT（exp 设为未来时间）
    const header = btoa(JSON.stringify({ alg: 'HS256' }))
    const payload = btoa(JSON.stringify({ sub: 'user1', exp: Math.floor(Date.now() / 1000) + 3600 }))
    store.rag_token = `${header}.${payload}.fakesig`

    router.push('/')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/')
  })

  it('allows access to login page without token', async () => {
    delete store.rag_token

    router.push('/login')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/login')
  })
})
