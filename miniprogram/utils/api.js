// 梦境博物馆 - API 封装
const BASE = 'https://dream-museum.onrender.com'
const REQ_TIMEOUT = 60000 // 60s 超时（Render 冷启动需要 15-30s）

function request(path, method, data) {
  return _doRequest(path, method, data).catch(err => {
    // 超时重试一次（Render 冷启动）
    if (err && (err.errMsg || '').indexOf('timeout') > -1) {
      console.log('请求超时，重试中...')
      return _doRequest(path, method, data)
    }
    return Promise.reject(err)
  })
}

function _doRequest(path, method, data) {
  return new Promise((resolve, reject) => {
    const token = wx.getStorageSync('token') || ''
    wx.request({
      url: BASE + path,
      method: method,
      data: data,
      timeout: REQ_TIMEOUT,
      header: {
        'Content-Type': 'application/json',
        'Authorization': token ? 'Bearer ' + token : ''
      },
      success(res) {
        if (res.statusCode === 200) {
          resolve(fixImageUrls(res.data))
        } else if (res.statusCode === 401) {
          wx.removeStorageSync('token')
          wx.showToast({ title: '请先登录', icon: 'none' })
          reject(res.data)
        } else {
          reject(res.data)
        }
      },
      fail(err) {
        // 区分超时和网络问题
        if (err.errMsg && err.errMsg.indexOf('timeout') > -1) {
          wx.showToast({ title: '连接超时，请稍后重试', icon: 'none' })
        } else {
          wx.showToast({ title: '网络异常，请检查网络', icon: 'none' })
        }
        reject(err)
      }
    })
  })
}

// 图片 URL 处理 — 外部图走代理，避免域名白名单问题
function fixImageUrls(obj) {
  if (!obj || typeof obj !== 'object') return obj
  if (Array.isArray(obj)) {
    return obj.map(fixImageUrls)
  }
  const o = {}
  for (const key of Object.keys(obj)) {
    const val = obj[key]

    if (key === 'image_url') {
      if (val && typeof val === 'string' && val.trim() !== '') {
        // 外部图片 URL（s3.siliconflow.cn 等）统一走代理
        if (val.startsWith('http') && val.indexOf(BASE) !== 0) {
          o[key] = BASE + '/api/image/' + obj.id
        } else {
          o[key] = val
        }
      } else if (obj.id) {
        // 空 URL 走代理兜底（返回占位图）
        o[key] = BASE + '/api/image/' + obj.id
      } else {
        o[key] = ''
      }
    } else if (typeof val === 'object' && val !== null) {
      o[key] = fixImageUrls(val)
    } else {
      o[key] = val
    }
  }
  return o
}

module.exports = {
  login(code) {
    return request('/api/auth/login', 'POST', { code: code })
  },

  createDream(prompt, style, isPublic) {
    return request('/api/dream/create', 'POST', {
      prompt: prompt, style: style || '梦核', is_public: isPublic || false
    })
  },

  getDreamList(page, keyword) {
    let url = '/api/dream/list?page=' + (page || 1) + '&size=20'
    if (keyword) url += '&keyword=' + encodeURIComponent(keyword)
    return request(url, 'GET')
  },

  getDreamDetail(id) {
    return request('/api/dream/detail/' + id, 'GET')
  },

  likeDream(dreamId) {
    return request('/api/dream/like', 'POST', { dream_id: dreamId })
  },

  favDream(dreamId) {
    return request('/api/dream/fav', 'POST', { dream_id: dreamId })
  },

  publishDream(dreamId) {
    return request('/api/dream/publish', 'POST', { dream_id: dreamId })
  },

  deleteDream(dreamId) {
    return request('/api/dream/delete', 'POST', { dream_id: dreamId })
  },

  adCallback() {
    return request('/api/ad/callback', 'POST', {})
  },

  getUserProfile() {
    return request('/api/user/profile', 'GET')
  },

  updateProfile(nickname, avatar) {
    return request('/api/user/update', 'POST', { nickname: nickname || '', avatar: avatar || '' })
  },

  getUserDreams(page) {
    return request('/api/user/dreams?page=' + (page || 1), 'GET')
  },

  getUserFavorites(page) {
    return request('/api/user/favorites?page=' + (page || 1), 'GET')
  }
}
