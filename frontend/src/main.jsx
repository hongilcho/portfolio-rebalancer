/**
 * React 웹 애플리케이션 진입점 (main.jsx)
 * ========================================
 * 루트 DOM 노드(#root)에 React 루트 컴포넌트(App)를 마운트하고 글로벌 CSS 스타일을 로드합니다.
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
