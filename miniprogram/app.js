// 梦境博物馆
App({
  onLaunch() {
    this.autoLogin()
  },

  autoLogin() {
    const token = wx.getStorageSync('token')
    if (token) return
    wx.login({
      success: (res) => {
        if (res.code) {
          const api = require('./utils/api')
          api.login(res.code).then(data => {
            if (data.token) {
              wx.setStorageSync('token', data.token)
              wx.setStorageSync('uid', data.user_id)
            }
          }).catch(() => {})
        }
      }
    })
  },

  globalData: {
    userInfo: null
  }
})
