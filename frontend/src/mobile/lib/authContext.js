import { createContext, useContext } from 'react';

export const AuthContext = createContext(null);
export const useMobileAuth = () => useContext(AuthContext);
