import { createRouter, createWebHistory } from 'vue-router'
import TemplateDisplayView from '../views/TemplateDisplayView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'template-display',
      component: TemplateDisplayView,
    },
  ],
})

export default router