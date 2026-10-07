import type {Metadata} from 'next';
import './globals.css';
export const metadata:Metadata={title:'星尘奇物铺 · 观店',description:'看点点经营星港里的小小奇物铺',icons:{icon:'/favicon.svg',shortcut:'/favicon.svg'}};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="zh-CN"><body>{children}</body></html>}
