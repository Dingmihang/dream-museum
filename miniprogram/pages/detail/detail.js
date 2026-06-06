const api = require('../../utils/api')

Page({
  data: {
    dream: null,
    dream_tags: [],
    isLiked: false,
    isFaved: false,
    loading: true
  },

  onLoad(options) {
    if (options.id) {
      this.loadDetail(options.id)
    }
  },

  loadDetail(id) {
    this.setData({ loading: true })
    api.getDreamDetail(id).then(res => {
      const dream = res.data
      this.setData({
        dream: dream,
        dream_tags: typeof dream.dream_tags === 'string' ? JSON.parse(dream.dream_tags || '[]') : (dream.dream_tags || []),
        isLiked: dream.is_liked || false,
        isFaved: dream.is_faved || false,
        loading: false
      })
    }).catch(() => {
      wx.showToast({ title: '加载失败', icon: 'none' })
      this.setData({ loading: false })
    })
  },

  onLike() {
    api.likeDream(this.data.dream.id).then(res => {
      this.setData({
        isLiked: res.liked,
        'dream.like_count': res.like_count
      })
    })
  },

  onFav() {
    api.favDream(this.data.dream.id).then(res => {
      this.setData({ isFaved: res.faved })
      wx.showToast({ title: res.faved ? '已收藏' : '已取消', icon: 'none' })
    })
  },

  onShareAppMessage() {
    return {
      title: this.data.dream ? this.data.dream.dream_title : '梦境博物馆',
      path: '/pages/detail/detail?id=' + this.data.dream.id,
      imageUrl: this.data.dream ? this.data.dream.image_url : ''
    }
  }
})
