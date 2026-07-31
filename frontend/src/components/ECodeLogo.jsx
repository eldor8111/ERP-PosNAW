/**
 * E-code Logo Component
 * Yangi dizayndagi PNG logo asosida
 */

export default function ECodeLogo({
  size = 40,
  showText = false, // Yangi logoda o'zining matni bor, qo'shimcha matn kerak emas
  textClassName = '',
  className = '',
}) {
  return (
    <div className={`flex items-center ${className}`}>
      <img 
        src="/logo.png" 
        alt="E-code ERP" 
        style={{ height: size }} 
        className="object-contain"
      />
      {showText && (
        <span className={`font-bold ml-2 text-slate-800 ${textClassName}`}>
          E-code
        </span>
      )}
    </div>
  );
}

export function ECodeIcon({ size = 32, className = '' }) {
  return (
    <div className={`inline-flex items-center ${className}`}>
       <img 
        src="/logo.png" 
        alt="E-code ERP" 
        style={{ height: size }} 
        className="object-contain"
      />
    </div>
  );
}

export function ECodeLogoPrimary({ size = 48, className = '' }) {
  return (
    <div className={`flex items-center ${className}`}>
      <img 
        src="/logo.png" 
        alt="E-code ERP" 
        style={{ height: size }} 
        className="object-contain filter drop-shadow-md"
      />
    </div>
  );
}

export function ECodeIconLight({ size = 64, className = '' }) {
  return (
    <div className={`inline-flex items-center ${className}`}>
       <img 
        src="/logo.png" 
        alt="E-code ERP" 
        style={{ height: size }} 
        className="object-contain drop-shadow-lg"
      />
    </div>
  );
}

