// 梦境博物馆
App({
  onLaunch() {
    this.checkLogin()
  },

  checkLogin() {
    const token = wx.getStorageSync('token')
    if (!token) {
      // 未登录，跳转登录页
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
