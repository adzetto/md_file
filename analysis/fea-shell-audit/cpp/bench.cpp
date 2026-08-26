#include "element.hpp"
#include <cstdio>
#include <chrono>
#include <random>
#include <vector>
#include <Eigen/Sparse>
#include <Eigen/Dense>

using clk = std::chrono::high_resolution_clock;
static double secs(clk::time_point a, clk::time_point b){
    return std::chrono::duration<double>(b-a).count(); }

void grad18(const double x[18], const double X[18], double E,double nu,double th,
            double g[18]) {
    Dual<18> xd[18], Xd[18];
    for(int i=0;i<18;++i){ xd[i]=Dual<18>(x[i]); xd[i].d[i]=1.0; Xd[i]=Dual<18>(X[i]); }
    Dual<18> W = patch_energy<Dual<18>>(xd, Xd, E, nu, th);
    for(int i=0;i<18;++i) g[i]=W.d[i];
}
void gradhess18(const double x[18], const double X[18], double E,double nu,double th,
                double g[18], double H[18][18]) {
    using D = Dual<18>; using DD = Dual2<18,18>;
    DD xd[18], Xd[18];
    for(int i=0;i<18;++i){
        xd[i]=DD(x[i]); xd[i].v.d[i]=1.0; xd[i].d[i]=D(1.0);
        Xd[i]=DD(X[i]);
    }
    DD W = patch_energy<DD>(xd, Xd, E, nu, th);
    for(int i=0;i<18;++i){ g[i]=W.v.d[i]; for(int j=0;j<18;++j) H[i][j]=W.d[i].d[j]; }
}

int main(int argc,char**argv){
    int NELEM = argc>1 ? atoi(argv[1]) : 4608;
    double E=3.10275e3, nu=0.3, th=12.7;
    std::mt19937 rng(1); std::normal_distribution<double> nd(0.,1.);
    double base[18]={0,0,0, 100,0,0, 0,100,0, 100,100,0, -100,100,0, 50,-100,0};
    std::vector<double> Xs(18*NELEM), xs(18*NELEM);
    for(int e=0;e<NELEM;++e) for(int i=0;i<18;++i){
        Xs[18*e+i]=base[i]+2.0*nd(rng); xs[18*e+i]=Xs[18*e+i]+0.5*nd(rng); }

    std::vector<double> G(18*NELEM); std::vector<double> KK(324*NELEM);
    double acc=0;
    // energy only
    auto t0=clk::now();
    for(int e=0;e<NELEM;++e) acc += patch_energy<double>(&xs[18*e], &Xs[18*e], E,nu,th);
    auto t1=clk::now();
    // gradient
    for(int e=0;e<NELEM;++e) grad18(&xs[18*e], &Xs[18*e], E,nu,th, &G[18*e]);
    auto t2=clk::now();
    // gradient + hessian
    double Hl[18][18];
    for(int e=0;e<NELEM;++e){ gradhess18(&xs[18*e], &Xs[18*e], E,nu,th, &G[18*e], Hl);
        for(int i=0;i<18;++i) for(int j=0;j<18;++j) KK[324*e+18*i+j]=Hl[i][j]; }
    auto t3=clk::now();

    printf("C++  nelem=%d  (single thread, -O3)\n", NELEM);
    printf("  energy only        : %8.4f s   %8.3f us/elem\n", secs(t0,t1), 1e6*secs(t0,t1)/NELEM);
    printf("  + gradient (f_int) : %8.4f s   %8.3f us/elem\n", secs(t1,t2), 1e6*secs(t1,t2)/NELEM);
    printf("  + Hessian  (K_e)   : %8.4f s   %8.3f us/elem\n", secs(t2,t3), 1e6*secs(t2,t3)/NELEM);
    printf("  (checksum %.6e)\n", acc);

    // ---- sparse assembly + factorisation with a synthetic connectivity ----
    int n = (int)std::sqrt((double)NELEM/2.0);
    int ndof = 3*(n+1)*(n+1);
    std::vector<Eigen::Triplet<double>> trip; trip.reserve(324*NELEM);
    std::vector<int> dofs(18);
    auto ta=clk::now();
    for(int e=0;e<NELEM;++e){
        for(int a=0;a<6;++a){ int nd_=(e*7+a*13)%((n+1)*(n+1));
            for(int k=0;k<3;++k) dofs[3*a+k]=3*nd_+k; }
        for(int i=0;i<18;++i) for(int j=0;j<18;++j)
            trip.emplace_back(dofs[i],dofs[j],KK[324*e+18*i+j]);
    }
    Eigen::SparseMatrix<double> A(ndof,ndof);
    A.setFromTriplets(trip.begin(),trip.end());
    for(int i=0;i<ndof;++i) A.coeffRef(i,i)+= 1e6;
    auto tb=clk::now();
    Eigen::SimplicialLDLT<Eigen::SparseMatrix<double>> solver;
    solver.compute(A);
    Eigen::VectorXd rhs=Eigen::VectorXd::Ones(ndof);
    Eigen::VectorXd sol=solver.solve(rhs);
    auto tc=clk::now();
    printf("  sparse assemble    : %8.4f s   (ndof=%d, nnz=%ld)\n", secs(ta,tb), ndof, (long)A.nonZeros());
    printf("  sparse LDLT+solve  : %8.4f s   (|u|=%.3e)\n", secs(tb,tc), sol.norm());
    return 0;
}
