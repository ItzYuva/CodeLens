export const environment = {
  production: false,
  apiUrl: '',
  wsUrl: `ws://${typeof window !== 'undefined' ? window.location.host : 'localhost:4200'}`,
};
