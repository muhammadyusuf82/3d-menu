import { createRoot } from 'react-dom/client';
import '@fontsource-variable/fraunces';
import '@fontsource-variable/outfit';
import './styles.css';
import './app.css';
import App from './App.tsx';

createRoot(document.getElementById('root')!).render(<App />);
