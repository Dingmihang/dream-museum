// 梦境博物馆
App({
  onLaunch() {
    this.warmupBackend()
    this.checkLogin()
  },

  warmupBackend() {
    const BASE = 'https://dream-museum.onrender.com'
    wx.request({
      url: BASE + '/health',
      timeout: 30000,
      success: () => console.log('后端已就绪'),
      fail: () => console.log('后端预热中...')
    })
  },

  checkLogin() {
    const token = wx.getStorageSync('token')
    if (!token) {
      wx.reLaunch({ url: '/pages/login/login' })
    }
  },

  logout() {
    wx.removeStorageSync('token')
    wx.removeStorageSync('uid')
    wx.reLaunch({ url: '/pages/login/login' })
  },

  globalData: {
    userInfo: null
  }
})
