import { Prism } from 'prism-react-renderer';

function exposePrism(): void {
  // Грамматики из пакета prismjs регистрируются через глобальный объект Prism.
  // Этот модуль импортируется раньше них, поэтому к моменту их выполнения
  // глобальный Prism уже указывает на экземпляр из prism-react-renderer.
  (globalThis as typeof globalThis & { Prism?: typeof Prism }).Prism = Prism;
}

exposePrism();
