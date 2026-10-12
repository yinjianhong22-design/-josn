import { createApp } from 'vue'
import App from './App.vue'
import router from './routers'
import './styles/global.css'

createApp(App).use(router).mount('#app')
