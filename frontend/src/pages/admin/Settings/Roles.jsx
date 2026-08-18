import React, { useState, useEffect } from 'react';
import { useLang } from '../../../context/LangContext';
import api from '../../../api/axios';
import toast from 'react-hot-toast';
import { 
  BriefcaseBusiness, Package, Users, Warehouse, 
  Wallet, FileText, Settings, Shield, Plus, X, 
  Edit3, Trash2, CheckCircle2, Search
} from 'lucide-react';

const MODULES = [
  { id: 'sales', name: 'Bitimlar (Sotuvlar)', icon: <BriefcaseBusiness className="w-5 h-5" /> },
  { id: 'products', name: 'Mahsulotlar', icon: <Package className="w-5 h-5" /> },
  { id: 'customers', name: 'Mijozlar', icon: <Users className="w-5 h-5" /> },
  { id: 'inventory', name: 'Omborxona', icon: <Warehouse className="w-5 h-5" /> },
  { id: 'finance', name: 'Moliya', icon: <Wallet className="w-5 h-5" /> },
  { id: 'reports', name: 'Hisobotlar', icon: <FileText className="w-5 h-5" /> },
  { id: 'settings', name: 'Sozlamalar', icon: <Settings className="w-5 h-5" /> },
];

const ACTIONS = [
  { id: 'view', name: "Ko'rish" },
  { id: 'create', name: 'Yaratish' },
  { id: 'edit', name: 'Tahrirlash' },
  { id: 'delete', name: "O'chirish" },
];

export default function RolesTab() {
  const { t } = useLang();
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingRole, setEditingRole] = useState(null);
  const [showSlideover, setShowSlideover] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  
  const [form, setForm] = useState({ name: '', permissions: {} });
  const [saving, setSaving] = useState(false);

  const fetchRoles = () => {
    setLoading(true);
    api.get('/roles/').then(r => setRoles(r.data)).finally(() => setLoading(false));
  };

  useEffect(() => { fetchRoles(); }, []);

  const openAdd = () => {
    setEditingRole(null);
    setForm({ name: '', permissions: {} });
    setShowSlideover(true);
  };

  const openEdit = (r) => {
    setEditingRole(r);
    setForm({ name: r.name, permissions: r.permissions || {} });
    setShowSlideover(true);
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Rostdan ham o'chirmoqchimisiz?")) return;
    try {
      await api.delete(`/roles/${id}`);
      setRoles(prev => prev.filter(r => r.id !== id));
      toast.success("Rol o'chirildi");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Xatolik yuz berdi");
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editingRole) {
        await api.put(`/roles/${editingRole.id}`, form);
        toast.success("Rol muvaffaqiyatli saqlandi");
      } else {
        await api.post('/roles/', form);
        toast.success("Yangi rol yaratildi");
      }
      setShowSlideover(false);
      fetchRoles();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Xatolik yuz berdi");
    } finally {
      setSaving(false);
    }
  };

  const togglePermission = (modId, actId, val) => {
    setForm(prev => {
      const perms = { ...prev.permissions };
      if (!perms[modId]) perms[modId] = {};
      perms[modId][actId] = val;
      return { ...prev, permissions: perms };
    });
  };

  const toggleModuleAll = (modId, val) => {
    setForm(prev => {
      const perms = { ...prev.permissions };
      if (!perms[modId]) perms[modId] = {};
      ACTIONS.forEach(a => perms[modId][a.id] = val);
      return { ...prev, permissions: perms };
    });
  };

  const filteredRoles = roles.filter(r => r.name.toLowerCase().includes(searchTerm.toLowerCase()));

  return (
    <div className="relative h-full flex flex-col">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
        <div>
          <h2 className="text-2xl font-black text-slate-800 tracking-tight">Rollar va Huquqlar</h2>
          <p className="text-sm text-slate-500 mt-1">Tizimdagi rollarni yarating va ruxsatlarni boshqaring</p>
        </div>
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <div className="relative w-full sm:w-64">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input 
              type="text" 
              placeholder="Rol qidirish..." 
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:bg-white focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 transition-all outline-none"
            />
          </div>
          <button 
            onClick={openAdd} 
            className="flex items-center gap-2 px-5 py-2.5 bg-slate-900 text-white rounded-xl text-sm font-semibold hover:bg-blue-600 hover:shadow-lg hover:shadow-blue-500/25 transition-all active:scale-95 whitespace-nowrap"
          >
            <Plus className="w-4 h-4" />
            Yangi rol
          </button>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {loading ? (
          <div className="col-span-full py-20 flex justify-center">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
          </div>
        ) : filteredRoles.length === 0 ? (
          <div className="col-span-full py-16 text-center bg-slate-50 border border-dashed border-slate-200 rounded-3xl">
            <Shield className="w-12 h-12 text-slate-300 mx-auto mb-4" />
            <h3 className="text-lg font-bold text-slate-600 mb-1">Rollar topilmadi</h3>
            <p className="text-slate-400 text-sm">Qidiruvga mos keladigan rol mavjud emas.</p>
          </div>
        ) : (
          filteredRoles.map(role => {
            const permCount = Object.keys(role.permissions || {}).length;
            const activeMods = Object.keys(role.permissions || {}).slice(0, 3);
            
            return (
              <div 
                key={role.id} 
                onClick={() => openEdit(role)}
                className="group relative bg-white rounded-3xl p-6 cursor-pointer border-2 border-transparent hover:border-blue-100 hover:shadow-[0_8px_30px_rgb(0,0,0,0.04)] transition-all duration-300 ring-1 ring-slate-200 flex flex-col"
              >
                <div className="absolute -top-10 -right-10 w-32 h-32 bg-gradient-to-br from-blue-50 to-blue-50 rounded-full blur-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>

                <div className="relative z-10 flex items-start justify-between mb-6">
                  <div className="flex items-center gap-4">
                    <div className={`w-14 h-14 rounded-2xl flex items-center justify-center shadow-sm transition-transform duration-300 group-hover:scale-110 ${role.is_system ? 'bg-gradient-to-br from-amber-400 to-orange-400 text-white shadow-amber-200' : 'bg-gradient-to-br from-blue-500 to-blue-500 text-white shadow-blue-200'}`}>
                      <Shield className="w-7 h-7 drop-shadow-md" />
                    </div>
                    <div>
                      <h3 className="text-xl font-bold text-slate-800 leading-tight mb-1 group-hover:text-blue-600 transition-colors">{role.name}</h3>
                      <div className="flex items-center gap-2 text-xs font-semibold">
                        {role.is_system ? (
                          <span className="text-amber-700 bg-amber-50 px-2.5 py-1 rounded-lg">Tizim roli</span>
                        ) : (
                          <span className="text-blue-700 bg-blue-50 px-2.5 py-1 rounded-lg">Kompaniya roli</span>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  <button className="w-10 h-10 rounded-full bg-slate-50 text-slate-400 flex items-center justify-center opacity-0 group-hover:opacity-100 hover:bg-blue-50 hover:text-blue-600 transition-all hover:scale-110">
                    <Edit3 className="w-4 h-4" />
                  </button>
                </div>
                
                <div className="relative z-10 flex-1">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-3">Ruxsat etilgan bo'limlar</p>
                  <div className="flex flex-wrap gap-2 mb-6">
                    {permCount === 0 ? (
                      <span className="text-sm font-medium text-slate-400 italic bg-slate-50 px-3 py-1.5 rounded-xl border border-slate-100">Hech qanday ruxsat yo'q</span>
                    ) : (
                      <>
                        {activeMods.map(mod => (
                          <span key={mod} className="px-3 py-1.5 bg-slate-50 border border-slate-200/60 text-slate-600 text-xs font-semibold rounded-xl shadow-sm group-hover:border-blue-100 group-hover:bg-blue-50/50 transition-colors">
                            {MODULES.find(m => m.id === mod)?.name || mod}
                          </span>
                        ))}
                        {permCount > 3 && (
                          <span className="px-3 py-1.5 bg-slate-100 text-slate-500 text-xs font-bold rounded-xl shadow-sm">
                            +{permCount - 3} ta
                          </span>
                        )}
                      </>
                    )}
                  </div>
                </div>

                <div className="relative z-10 pt-4 border-t border-slate-100 flex items-center justify-between mt-auto">
                  <div className="flex items-center gap-2 text-slate-500">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                    <span className="text-xs font-bold">{permCount} ta modul sozlangan</span>
                  </div>
                  
                  {!role.is_system && (
                    <button 
                      onClick={(e) => { e.stopPropagation(); handleDelete(role.id); }} 
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold text-slate-400 hover:text-white hover:bg-blue-500 rounded-lg transition-all"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      O'chirish
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      <div className={`fixed inset-0 z-50 transition-all duration-300 ${showSlideover ? 'opacity-100 visible' : 'opacity-0 invisible'}`}>
        <div className="absolute inset-0 bg-slate-900/20 backdrop-blur-sm" onClick={() => setShowSlideover(false)}></div>
        
        <div className={`absolute top-0 right-0 bottom-0 w-full max-w-xl bg-white shadow-2xl transition-transform duration-300 ease-in-out flex flex-col ${showSlideover ? 'translate-x-0' : 'translate-x-full'}`}>
          <div className="px-8 py-6 border-b border-slate-100 flex items-center justify-between bg-white z-10">
            <div>
              <h3 className="text-xl font-black text-slate-800">
                {editingRole ? 'Rolni tahrirlash' : 'Yangi rol'}
              </h3>
              <p className="text-sm text-slate-500 mt-1">{editingRole ? editingRole.name : "Yangi rol va uning huquqlari"}</p>
            </div>
            <button 
              onClick={() => setShowSlideover(false)} 
              className="w-10 h-10 rounded-full bg-slate-100 text-slate-500 flex items-center justify-center hover:bg-slate-200 hover:text-slate-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          
          <div className="flex-1 overflow-y-auto bg-slate-50/50 px-8 py-6">
            <form id="roleForm" onSubmit={handleSave} className="space-y-8">
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-2">Rolning nomi</label>
                <input 
                  required 
                  value={form.name} 
                  onChange={e => setForm({...form, name: e.target.value})} 
                  placeholder="Masalan: Boshqaruvchi" 
                  disabled={editingRole?.is_system}
                  className="w-full px-5 py-3.5 bg-white border border-slate-200 rounded-2xl text-[15px] font-medium text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-500/10 focus:border-blue-500 transition-all shadow-sm disabled:bg-slate-100 disabled:text-slate-500"
                />
              </div>
              
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h4 className="text-sm font-bold text-slate-800">Modullar bo'yicha ruxsatlar</h4>
                </div>
                
                <div className="space-y-4">
                  {MODULES.map(mod => {
                    const isAllSelected = ACTIONS.every(a => form.permissions?.[mod.id]?.[a.id]);
                    const isSomeSelected = ACTIONS.some(a => form.permissions?.[mod.id]?.[a.id]);

                    return (
                      <div key={mod.id} className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm hover:border-blue-200 transition-colors">
                        <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/80 flex items-center justify-between cursor-pointer" onClick={() => toggleModuleAll(mod.id, !isAllSelected)}>
                          <div className="flex items-center gap-3">
                            <div className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${isSomeSelected ? 'bg-blue-100 text-blue-600' : 'bg-white border border-slate-200 text-slate-400'}`}>
                              {mod.icon}
                            </div>
                            <span className="font-bold text-slate-700">{mod.name}</span>
                          </div>
                          
                          <div className={`w-6 h-6 rounded-md flex items-center justify-center transition-all ${isAllSelected ? 'bg-blue-600 text-white' : isSomeSelected ? 'bg-blue-100 text-blue-600' : 'border-2 border-slate-200 text-transparent'}`}>
                            <CheckCircle2 className="w-4 h-4" />
                          </div>
                        </div>
                        
                        <div className="p-5">
                          <div className="grid grid-cols-2 gap-4">
                            {ACTIONS.map(act => {
                              const isActive = !!form.permissions?.[mod.id]?.[act.id];
                              return (
                                <label 
                                  key={act.id} 
                                  className={`flex items-center justify-between p-3 rounded-xl cursor-pointer border transition-all ${isActive ? 'bg-blue-50/50 border-blue-200 shadow-sm' : 'bg-white border-slate-100 hover:border-slate-200 hover:bg-slate-50'}`}
                                >
                                  <span className={`text-sm font-semibold transition-colors ${isActive ? 'text-blue-900' : 'text-slate-600'}`}>
                                    {act.name}
                                  </span>
                                  <button
                                    type="button"
                                    onClick={() => togglePermission(mod.id, act.id, !isActive)}
                                    className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${isActive ? 'bg-blue-600' : 'bg-slate-200'}`}
                                  >
                                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${isActive ? 'translate-x-5' : 'translate-x-1'}`} />
                                  </button>
                                </label>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </form>
          </div>
          
          <div className="px-8 py-5 border-t border-slate-100 bg-white flex items-center justify-end gap-4 z-10 shadow-[0_-10px_20px_-10px_rgba(0,0,0,0.05)]">
            <button 
              type="button" 
              onClick={() => setShowSlideover(false)} 
              className="px-6 py-3 text-slate-600 hover:bg-slate-100 font-bold text-sm rounded-xl transition-colors"
            >
              Bekor qilish
            </button>
            <button 
              type="submit" 
              form="roleForm" 
              disabled={saving} 
              className="px-8 py-3 bg-slate-900 hover:bg-blue-600 text-white font-bold text-sm rounded-xl transition-all shadow-lg hover:shadow-blue-500/25 active:scale-95 disabled:opacity-70 flex items-center gap-2"
            >
              {saving ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                  Saqlanmoqda...
                </>
              ) : 'Saqlash'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
