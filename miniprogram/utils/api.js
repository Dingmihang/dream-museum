// 梦境博物馆 - API 封装
const BASE = 'https://dream-museum.onrender.com'

function request(path, method, data) {
  return new Promise((resolve, reject) => {
    const token = wx.getStorageSync('token') || ''
    wx.request({
      url: BASE + path,
      method: method,
      data: data,
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
        wx.showToast({ title: '网络异常', icon: 'none' })
        reject(err)
      }
    })
  })
}

// 图片走代理，解决域名白名单问题
function fixImageUrls(obj) {
  if (!obj || typeof obj !== 'object') return obj
  if (Array.isArray(obj)) {
    return obj.map(fixImageUrls)
  }
  const o = {}
  for (const key of Object.keys(obj)) {
    const val = obj[key]
    if (key === 'image_url' && val && val.startsWith('http')) {
      // 提取 dream id，替换为代理 URL
      if (obj.id) {
        o[key] = BASE + '/api/image/' + obj.id
      } else {
        o[key] = val
      }
    } else if (typeof val === 'object') {
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
