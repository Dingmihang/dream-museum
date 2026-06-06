const api = require('../../utils/api')

Page({
  data: {
    dreams: [],
    page: 1,
    hasMore: true,
    loading: true,
    keyword: ''
  },

  onLoad() {
    this.loadDreams()
  },

  onShow() {
    // 从创造页返回时刷新
    if (this.data.page === 1 && this.data.dreams.length > 0) {
      this.setData({ page: 1, dreams: [], hasMore: true })
      this.loadDreams()
    }
  },

  onPullDownRefresh() {
    this.setData({ page: 1, dreams: [], hasMore: true })
    this.loadDreams()
    wx.stopPullDownRefresh()
  },

  loadDreams() {
    if (!this.data.hasMore) return
    this.setData({ loading: true })
    api.getDreamList(this.data.page, this.data.keyword).then(res => {
      const dreams = res.data.map(d => ({
        ...d,
        dream_tags: typeof d.dream_tags === 'string' ? JSON.parse(d.dream_tags || '[]') : (d.dream_tags || [])
      }))
      this.setData({
        dreams: this.data.page === 1 ? dreams : this.data.dreams.concat(dreams),
        hasMore: res.has_more,
        loading: false
      })
    }).catch(() => {
      this.setData({ loading: false })
    })
  },

  loadMore() {
    if (!this.data.hasMore) return
    this.setData({ page: this.data.page + 1 }, () => {
      this.loadDreams()
    })
  },

  onSearch(e) {
    this.setData({ keyword: e.detail.value })
  },

  doSearch() {
    this.setData({ page: 1, dreams: [], hasMore: true })
    this.loadDreams()
  },

  onLike(e) {
    const id = e.currentTarget.dataset.id
    api.likeDream(id).then(res => {
      const dreams = this.data.dreams.map(d => {
        if (d.id === id) d.like_count = res.like_count
        return d
      })
      this.setData({ dreams })
    })
  },

  goDetail(e) {
    wx.navigateTo({ url: '/pages/detail/detail?id=' + e.currentTarget.dataset.id })
  }
})
