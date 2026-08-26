// Rotation-free 6-node shell patch: strain energy, templated on the scalar type,
// so the same source yields value / gradient / Hessian through forward-mode AD.
#pragma once
#include <cmath>
#include <array>

template <int N> struct Dual {
    double v; std::array<double, N> d;
    Dual() : v(0) { d.fill(0.0); }
    Dual(double x) : v(x) { d.fill(0.0); }
};
template <int N> inline Dual<N> operator+(const Dual<N>& a, const Dual<N>& b){
    Dual<N> r; r.v=a.v+b.v; for(int i=0;i<N;++i) r.d[i]=a.d[i]+b.d[i]; return r; }
template <int N> inline Dual<N> operator-(const Dual<N>& a, const Dual<N>& b){
    Dual<N> r; r.v=a.v-b.v; for(int i=0;i<N;++i) r.d[i]=a.d[i]-b.d[i]; return r; }
template <int N> inline Dual<N> operator-(const Dual<N>& a){
    Dual<N> r; r.v=-a.v; for(int i=0;i<N;++i) r.d[i]=-a.d[i]; return r; }
template <int N> inline Dual<N> operator*(const Dual<N>& a, const Dual<N>& b){
    Dual<N> r; r.v=a.v*b.v; for(int i=0;i<N;++i) r.d[i]=a.d[i]*b.v+a.v*b.d[i]; return r; }
template <int N> inline Dual<N> operator/(const Dual<N>& a, const Dual<N>& b){
    Dual<N> r; double inv=1.0/b.v; r.v=a.v*inv;
    for(int i=0;i<N;++i) r.d[i]=(a.d[i]-r.v*b.d[i])*inv; return r; }
template <int N> inline Dual<N> sqrt(const Dual<N>& a){
    Dual<N> r; r.v=std::sqrt(a.v); double c=0.5/r.v;
    for(int i=0;i<N;++i) r.d[i]=a.d[i]*c; return r; }
template <int N> inline Dual<N> operator*(double s, const Dual<N>& a){
    Dual<N> r; r.v=s*a.v; for(int i=0;i<N;++i) r.d[i]=s*a.d[i]; return r; }

// nested duals: Dual<M> of Dual<N>
template <int M, int N> struct Dual2 {
    Dual<N> v; std::array<Dual<N>, M> d;
    Dual2() {} Dual2(double x) : v(x) {}
};
template <int M,int N> inline Dual2<M,N> operator+(const Dual2<M,N>&a,const Dual2<M,N>&b){
    Dual2<M,N> r; r.v=a.v+b.v; for(int i=0;i<M;++i) r.d[i]=a.d[i]+b.d[i]; return r;}
template <int M,int N> inline Dual2<M,N> operator-(const Dual2<M,N>&a,const Dual2<M,N>&b){
    Dual2<M,N> r; r.v=a.v-b.v; for(int i=0;i<M;++i) r.d[i]=a.d[i]-b.d[i]; return r;}
template <int M,int N> inline Dual2<M,N> operator-(const Dual2<M,N>&a){
    Dual2<M,N> r; r.v=-a.v; for(int i=0;i<M;++i) r.d[i]=-a.d[i]; return r;}
template <int M,int N> inline Dual2<M,N> operator*(const Dual2<M,N>&a,const Dual2<M,N>&b){
    Dual2<M,N> r; r.v=a.v*b.v; for(int i=0;i<M;++i) r.d[i]=a.d[i]*b.v+a.v*b.d[i]; return r;}
template <int M,int N> inline Dual2<M,N> operator/(const Dual2<M,N>&a,const Dual2<M,N>&b){
    Dual2<M,N> r; Dual<N> one(1.0); Dual<N> inv=one/b.v; r.v=a.v*inv;
    for(int i=0;i<M;++i) r.d[i]=(a.d[i]-r.v*b.d[i])*inv; return r;}
template <int M,int N> inline Dual2<M,N> sqrt(const Dual2<M,N>&a){
    Dual2<M,N> r; r.v=sqrt(a.v); Dual<N> half(0.5); Dual<N> c=half/r.v;
    for(int i=0;i<M;++i) r.d[i]=a.d[i]*c; return r;}
template <int M,int N> inline Dual2<M,N> operator*(double s, const Dual2<M,N>&a){
    Dual2<M,N> r; r.v=s*a.v; for(int i=0;i<M;++i) r.d[i]=s*a.d[i]; return r;}

inline double sqrt_(double a){ return std::sqrt(a); }
template<class T> inline T sqrt_(const T& a){ return sqrt(a); }

// ---------------------------------------------------------------- element
template <class T>
static inline void cross3(const T a[3], const T b[3], T c[3]) {
    c[0]=a[1]*b[2]-a[2]*b[1]; c[1]=a[2]*b[0]-a[0]*b[2]; c[2]=a[0]*b[1]-a[1]*b[0];
}
template <class T>
static inline T dot3(const T a[3], const T b[3]) { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }

// curvature (4 Voigt) + metric g + inverse metric, for one configuration
template <class T>
static void patch_curv(const T X[18], T c[4], T g[4], T gi[4]) {
    T a1[3],a2[3];
    for(int k=0;k<3;++k){ a1[k]=X[3+k]-X[k]; a2[k]=X[6+k]-X[k]; }
    T ncr[3]; cross3(a1,a2,ncr);
    T nn = sqrt_(dot3(ncr,ncr));
    T n[3]; for(int k=0;k<3;++k) n[k]=ncr[k]/nn;
    g[0]=dot3(a1,a1); g[1]=dot3(a1,a2); g[2]=g[1]; g[3]=dot3(a2,a2);
    T det = g[0]*g[3]-g[1]*g[2];
    gi[0]= g[3]/det; gi[1]= T(0.0)-g[1]/det; gi[2]=gi[1]; gi[3]= g[0]/det;
    T c1[3],c2[3];
    for(int k=0;k<3;++k){ c1[k]=gi[0]*a1[k]+gi[1]*a2[k]; c2[k]=gi[2]*a1[k]+gi[3]*a2[k]; }
    T b[3][3];
    for(int k=0;k<3;++k){ b[0][k]=X[9+k]-X[3+k]; b[1][k]=X[12+k]-X[6+k]; b[2][k]=X[15+k]-X[k]; }
    T xi[3],et[3],z[3];
    T off1[3]={T(1.0),T(0.0),T(0.0)}, off2[3]={T(0.0),T(1.0),T(0.0)};
    for(int i=0;i<3;++i){ xi[i]=dot3(b[i],c1)+off1[i]; et[i]=dot3(b[i],c2)+off2[i]; z[i]=dot3(b[i],n); }
    // 3x3 solve  T v = z ,  T_i = [xi^2-xi, et^2-et, xi*et]
    T M[3][3];
    for(int i=0;i<3;++i){ M[i][0]=xi[i]*xi[i]-xi[i]; M[i][1]=et[i]*et[i]-et[i]; M[i][2]=xi[i]*et[i]; }
    T d = M[0][0]*(M[1][1]*M[2][2]-M[1][2]*M[2][1])
        - M[0][1]*(M[1][0]*M[2][2]-M[1][2]*M[2][0])
        + M[0][2]*(M[1][0]*M[2][1]-M[1][1]*M[2][0]);
    T v0 = ( z[0]*(M[1][1]*M[2][2]-M[1][2]*M[2][1])
           - M[0][1]*(z[1]*M[2][2]-M[1][2]*z[2])
           + M[0][2]*(z[1]*M[2][1]-M[1][1]*z[2]) )/d;
    T v1 = ( M[0][0]*(z[1]*M[2][2]-M[1][2]*z[2])
           - z[0]*(M[1][0]*M[2][2]-M[1][2]*M[2][0])
           + M[0][2]*(M[1][0]*z[2]-z[1]*M[2][0]) )/d;
    T v2 = ( M[0][0]*(M[1][1]*z[2]-z[1]*M[2][1])
           - M[0][1]*(M[1][0]*z[2]-z[1]*M[2][0])
           + z[0]*(M[1][0]*M[2][1]-M[1][1]*M[2][0]) )/d;
    c[0]=2.0*v0; c[1]=2.0*v1; c[2]=v2; c[3]=v2;
}

template <class T>
T patch_energy(const T x[18], const T Xr[18], double E, double nu, double th) {
    T cc[4],gc[4],gic[4], cr[4],gr[4],gir[4];
    patch_curv(x ,cc,gc,gic);
    patch_curv(Xr,cr,gr,gir);
    T m[4]; m[0]=0.5*(gc[0]-gr[0]); m[1]=0.5*(gc[3]-gr[3]);
            m[2]=0.5*(gc[1]-gr[1]); m[3]=0.5*(gc[2]-gr[2]);
    T kb[4]; for(int i=0;i<4;++i) kb[i]=cr[i]-cc[i];
    const int pa[4]={0,1,0,1}, pb[4]={0,1,1,0};
    T Hm(0.0), Hb(0.0);
    T sm(0.0), sb(0.0);
    for(int i=0;i<4;++i) for(int j=0;j<4;++j){
        int a=pa[i],b=pb[i],c2=pa[j],d=pb[j];
        T h = nu*gir[a*2+b]*gir[c2*2+d]
            + (0.5*(1.0-nu))*(gir[a*2+c2]*gir[b*2+d] + gir[a*2+d]*gir[b*2+c2]);
        sm = sm + m[i]*h*m[j];
        sb = sb + kb[i]*h*kb[j];
    }
    T det = gr[0]*gr[3]-gr[1]*gr[2];
    T area = 0.5*sqrt_(det);
    double Km = E*th/(1.0-nu*nu), Kbd = E*th*th*th/(12.0*(1.0-nu*nu));
    return area*(0.5*Km*sm + 0.5*Kbd*sb);
}
