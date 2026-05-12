/**
 * API 模块单元测试
 * 验证 axios 拦截器、token 注入、统一响应解构、401 跳转
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock sessionStorage (token/user)
const store = {}
const sessionStorageMock = {
  getItem: vi.fn((key) => store[key] ?? null),
  setItem: vi.fn((key, val) => { store[key] = val }),
  removeItem: vi.fn((key) => { delete store[key] }),
}
Object.defineProperty(globalThis, 'sessionStorage', { value: sessionStorageMock })
Object.defineProperty(globalThis, 'window', {
  value: { location: { href: '', pathname: '/docs' } },
  writable: true,
})

// Mock axios 拦截器链
let requestInterceptor
let responseSuccessInterceptor
let responseErrorInterceptor

vi.mock('axios', () => {
  const instance = {
    interceptors: {
      request: { use: vi.fn((fn) => { requestInterceptor = fn }) },
      response: { use: vi.fn((ok, err) => { responseSuccessInterceptor = ok; responseErrorInterceptor = err }) },
    },
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  }
  return {
    default: {
      create: vi.fn(() => instance),
      get: vi.fn(),
    },
  }
})

describe('API interceptors', () => {
  beforeEach(async () => {
    vi.resetModules()
    Object.keys(store).forEach(k => delete store[k])
    // 动态导入以触发拦截器注册
    await import('../../api/index.js')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('request interceptor injects Authorization header when token exists', () => {
    store.rag_token = 'test-jwt-token'
    const cfg = { headers: {} }
    const result = requestInterceptor(cfg)
    expect(result.headers.Authorization).toBe('Bearer test-jwt-token')
  })

  it('request interceptor skips header when no token', () => {
    const cfg = { headers: {} }
    const result = requestInterceptor(cfg)
    expect(result.headers.Authorization).toBeUndefined()
  })

  it('response interceptor unwraps standard {code, data} body', () => {
    const response = {
      data: {
        code: 0,
        message: 'ok',
        data: { id: '123', name: 'test' },
        trace_id: 'abc-trace',
      },
    }
    const result = responseSuccessInterceptor(response)
    expect(result.id).toBe('123')
    expect(result.trace_id).toBe('abc-trace')
  })

  it('response interceptor passes through non-standard body', () => {
    const response = { data: 'raw string' }
    const result = responseSuccessInterceptor(response)
    expect(result).toBe('raw string')
  })

  it('response error interceptor clears token on 401', async () => {
    const error = {
      response: { status: 401, data: { message: 'Unauthorized' } },
    }
    await expect(responseErrorInterceptor(error)).rejects.toBe('Unauthorized')
    expect(sessionStorageMock.removeItem).toHaveBeenCalledWith('rag_token')
    expect(sessionStorageMock.removeItem).toHaveBeenCalledWith('rag_user')
  })
})
