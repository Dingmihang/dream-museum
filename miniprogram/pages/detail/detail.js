const api = require('../../utils/api')

Page({
  data: {
    dream: null,
    dream_tags: [],
    isLiked: false,
    isFaved: false,
    loading: true,
    imageFailed: false
  },

  onLoad(options) {
    if (options.id) {
      wx.nextTick(() => {
        this.loadDetail(options.id)
      })
    } else {
      this.setData({ loading: false })
    }
  },

  loadDetail(id) {
    this.setData({ loading: true, imageFailed: false })
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

  onImageError() {
    this.setData({ imageFailed: true })
  },

  onLike() {
    if (!this.data.dream) return
    api.likeDream(this.data.dream.id).then(res => {
      this.setData({
        isLiked: res.liked,
        'dream.like_count': res.like_count
      })
    }).catch(() => {})
  },

  onFav() {
    if (!this.data.dream) return
    api.favDream(this.data.dream.id).then(res => {
      this.setData({ isFaved: res.faved })
      wx.showToast({ title: res.faved ? '已收藏' : '已取消', icon: 'none' })
    }).catch(() => {})
  },

  onShareAppMessage() {
    if (!this.data.dream) return {}
    return {
      title: this.data.dream.dream_title || '梦境博物馆',
      path: '/pages/detail/detail?id=' + this.data.dream.id,
      imageUrl: this.data.dream.image_url || ''
    }
  }
})
