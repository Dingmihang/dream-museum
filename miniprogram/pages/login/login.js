const api = require('../../utils/api')

Page({
  data: {
    loading: false,
    errorMsg: ''
  },

  doLogin() {
    if (this.data.loading) return
    this.setData({ loading: true, errorMsg: '' })

    wx.login({
      success: (res) => {
        if (!res.code) {
          this.setData({ loading: false, errorMsg: '获取登录凭证失败' })
          return
        }
        api.login(res.code).then(data => {
          if (data.token) {
            wx.setStorageSync('token', data.token)
            wx.setStorageSync('uid', data.user_id)
            wx.showToast({ title: '登录成功', icon: 'success', duration: 1000 })
            setTimeout(() => {
              wx.switchTab({ url: '/pages/index/index' })
            }, 1000)
          } else {
            this.setData({ loading: false, errorMsg: '登录失败，请重试' })
          }
        }).catch(() => {
          this.setData({ loading: false, errorMsg: '网络异常，请重试' })
        })
      },
      fail: () => {
        this.setData({ loading: false, errorMsg: '微信登录失败' })
      }
    })
  }
})
