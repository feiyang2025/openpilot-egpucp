#include "car.h"

namespace {
#define DIM 9
#define EDIM 9
#define MEDIM 9
typedef void (*Hfun)(double *, double *, double *);

double mass;

void set_mass(double x){ mass = x;}

double rotational_inertia;

void set_rotational_inertia(double x){ rotational_inertia = x;}

double center_to_front;

void set_center_to_front(double x){ center_to_front = x;}

double center_to_rear;

void set_center_to_rear(double x){ center_to_rear = x;}

double stiffness_front;

void set_stiffness_front(double x){ stiffness_front = x;}

double stiffness_rear;

void set_stiffness_rear(double x){ stiffness_rear = x;}
const static double MAHA_THRESH_25 = 3.8414588206941227;
const static double MAHA_THRESH_24 = 5.991464547107981;
const static double MAHA_THRESH_30 = 3.8414588206941227;
const static double MAHA_THRESH_26 = 3.8414588206941227;
const static double MAHA_THRESH_27 = 3.8414588206941227;
const static double MAHA_THRESH_29 = 3.8414588206941227;
const static double MAHA_THRESH_28 = 3.8414588206941227;
const static double MAHA_THRESH_31 = 3.8414588206941227;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_5621847562774482709) {
   out_5621847562774482709[0] = delta_x[0] + nom_x[0];
   out_5621847562774482709[1] = delta_x[1] + nom_x[1];
   out_5621847562774482709[2] = delta_x[2] + nom_x[2];
   out_5621847562774482709[3] = delta_x[3] + nom_x[3];
   out_5621847562774482709[4] = delta_x[4] + nom_x[4];
   out_5621847562774482709[5] = delta_x[5] + nom_x[5];
   out_5621847562774482709[6] = delta_x[6] + nom_x[6];
   out_5621847562774482709[7] = delta_x[7] + nom_x[7];
   out_5621847562774482709[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_6433411341470746887) {
   out_6433411341470746887[0] = -nom_x[0] + true_x[0];
   out_6433411341470746887[1] = -nom_x[1] + true_x[1];
   out_6433411341470746887[2] = -nom_x[2] + true_x[2];
   out_6433411341470746887[3] = -nom_x[3] + true_x[3];
   out_6433411341470746887[4] = -nom_x[4] + true_x[4];
   out_6433411341470746887[5] = -nom_x[5] + true_x[5];
   out_6433411341470746887[6] = -nom_x[6] + true_x[6];
   out_6433411341470746887[7] = -nom_x[7] + true_x[7];
   out_6433411341470746887[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_1549433459195114425) {
   out_1549433459195114425[0] = 1.0;
   out_1549433459195114425[1] = 0.0;
   out_1549433459195114425[2] = 0.0;
   out_1549433459195114425[3] = 0.0;
   out_1549433459195114425[4] = 0.0;
   out_1549433459195114425[5] = 0.0;
   out_1549433459195114425[6] = 0.0;
   out_1549433459195114425[7] = 0.0;
   out_1549433459195114425[8] = 0.0;
   out_1549433459195114425[9] = 0.0;
   out_1549433459195114425[10] = 1.0;
   out_1549433459195114425[11] = 0.0;
   out_1549433459195114425[12] = 0.0;
   out_1549433459195114425[13] = 0.0;
   out_1549433459195114425[14] = 0.0;
   out_1549433459195114425[15] = 0.0;
   out_1549433459195114425[16] = 0.0;
   out_1549433459195114425[17] = 0.0;
   out_1549433459195114425[18] = 0.0;
   out_1549433459195114425[19] = 0.0;
   out_1549433459195114425[20] = 1.0;
   out_1549433459195114425[21] = 0.0;
   out_1549433459195114425[22] = 0.0;
   out_1549433459195114425[23] = 0.0;
   out_1549433459195114425[24] = 0.0;
   out_1549433459195114425[25] = 0.0;
   out_1549433459195114425[26] = 0.0;
   out_1549433459195114425[27] = 0.0;
   out_1549433459195114425[28] = 0.0;
   out_1549433459195114425[29] = 0.0;
   out_1549433459195114425[30] = 1.0;
   out_1549433459195114425[31] = 0.0;
   out_1549433459195114425[32] = 0.0;
   out_1549433459195114425[33] = 0.0;
   out_1549433459195114425[34] = 0.0;
   out_1549433459195114425[35] = 0.0;
   out_1549433459195114425[36] = 0.0;
   out_1549433459195114425[37] = 0.0;
   out_1549433459195114425[38] = 0.0;
   out_1549433459195114425[39] = 0.0;
   out_1549433459195114425[40] = 1.0;
   out_1549433459195114425[41] = 0.0;
   out_1549433459195114425[42] = 0.0;
   out_1549433459195114425[43] = 0.0;
   out_1549433459195114425[44] = 0.0;
   out_1549433459195114425[45] = 0.0;
   out_1549433459195114425[46] = 0.0;
   out_1549433459195114425[47] = 0.0;
   out_1549433459195114425[48] = 0.0;
   out_1549433459195114425[49] = 0.0;
   out_1549433459195114425[50] = 1.0;
   out_1549433459195114425[51] = 0.0;
   out_1549433459195114425[52] = 0.0;
   out_1549433459195114425[53] = 0.0;
   out_1549433459195114425[54] = 0.0;
   out_1549433459195114425[55] = 0.0;
   out_1549433459195114425[56] = 0.0;
   out_1549433459195114425[57] = 0.0;
   out_1549433459195114425[58] = 0.0;
   out_1549433459195114425[59] = 0.0;
   out_1549433459195114425[60] = 1.0;
   out_1549433459195114425[61] = 0.0;
   out_1549433459195114425[62] = 0.0;
   out_1549433459195114425[63] = 0.0;
   out_1549433459195114425[64] = 0.0;
   out_1549433459195114425[65] = 0.0;
   out_1549433459195114425[66] = 0.0;
   out_1549433459195114425[67] = 0.0;
   out_1549433459195114425[68] = 0.0;
   out_1549433459195114425[69] = 0.0;
   out_1549433459195114425[70] = 1.0;
   out_1549433459195114425[71] = 0.0;
   out_1549433459195114425[72] = 0.0;
   out_1549433459195114425[73] = 0.0;
   out_1549433459195114425[74] = 0.0;
   out_1549433459195114425[75] = 0.0;
   out_1549433459195114425[76] = 0.0;
   out_1549433459195114425[77] = 0.0;
   out_1549433459195114425[78] = 0.0;
   out_1549433459195114425[79] = 0.0;
   out_1549433459195114425[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_6294660566595538893) {
   out_6294660566595538893[0] = state[0];
   out_6294660566595538893[1] = state[1];
   out_6294660566595538893[2] = state[2];
   out_6294660566595538893[3] = state[3];
   out_6294660566595538893[4] = state[4];
   out_6294660566595538893[5] = dt*((-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]))*state[6] - 9.8100000000000005*state[8] + stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*state[1]) + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*state[4])) + state[5];
   out_6294660566595538893[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_6294660566595538893[7] = state[7];
   out_6294660566595538893[8] = state[8];
}
void F_fun(double *state, double dt, double *out_1214373718580184770) {
   out_1214373718580184770[0] = 1;
   out_1214373718580184770[1] = 0;
   out_1214373718580184770[2] = 0;
   out_1214373718580184770[3] = 0;
   out_1214373718580184770[4] = 0;
   out_1214373718580184770[5] = 0;
   out_1214373718580184770[6] = 0;
   out_1214373718580184770[7] = 0;
   out_1214373718580184770[8] = 0;
   out_1214373718580184770[9] = 0;
   out_1214373718580184770[10] = 1;
   out_1214373718580184770[11] = 0;
   out_1214373718580184770[12] = 0;
   out_1214373718580184770[13] = 0;
   out_1214373718580184770[14] = 0;
   out_1214373718580184770[15] = 0;
   out_1214373718580184770[16] = 0;
   out_1214373718580184770[17] = 0;
   out_1214373718580184770[18] = 0;
   out_1214373718580184770[19] = 0;
   out_1214373718580184770[20] = 1;
   out_1214373718580184770[21] = 0;
   out_1214373718580184770[22] = 0;
   out_1214373718580184770[23] = 0;
   out_1214373718580184770[24] = 0;
   out_1214373718580184770[25] = 0;
   out_1214373718580184770[26] = 0;
   out_1214373718580184770[27] = 0;
   out_1214373718580184770[28] = 0;
   out_1214373718580184770[29] = 0;
   out_1214373718580184770[30] = 1;
   out_1214373718580184770[31] = 0;
   out_1214373718580184770[32] = 0;
   out_1214373718580184770[33] = 0;
   out_1214373718580184770[34] = 0;
   out_1214373718580184770[35] = 0;
   out_1214373718580184770[36] = 0;
   out_1214373718580184770[37] = 0;
   out_1214373718580184770[38] = 0;
   out_1214373718580184770[39] = 0;
   out_1214373718580184770[40] = 1;
   out_1214373718580184770[41] = 0;
   out_1214373718580184770[42] = 0;
   out_1214373718580184770[43] = 0;
   out_1214373718580184770[44] = 0;
   out_1214373718580184770[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/(mass*state[1]) + (-stiffness_front - stiffness_rear)*state[5]/(mass*state[4]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/(mass*state[4]));
   out_1214373718580184770[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*pow(state[1], 2));
   out_1214373718580184770[47] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_1214373718580184770[48] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_1214373718580184770[49] = dt*((-1 - (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*pow(state[4], 2)))*state[6] - (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*pow(state[4], 2)));
   out_1214373718580184770[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/(mass*state[4]) + 1;
   out_1214373718580184770[51] = dt*(-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]));
   out_1214373718580184770[52] = dt*stiffness_front*state[0]/(mass*state[1]);
   out_1214373718580184770[53] = -9.8100000000000005*dt;
   out_1214373718580184770[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_1214373718580184770[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_1214373718580184770[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_1214373718580184770[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_1214373718580184770[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_1214373718580184770[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_1214373718580184770[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_1214373718580184770[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_1214373718580184770[62] = 0;
   out_1214373718580184770[63] = 0;
   out_1214373718580184770[64] = 0;
   out_1214373718580184770[65] = 0;
   out_1214373718580184770[66] = 0;
   out_1214373718580184770[67] = 0;
   out_1214373718580184770[68] = 0;
   out_1214373718580184770[69] = 0;
   out_1214373718580184770[70] = 1;
   out_1214373718580184770[71] = 0;
   out_1214373718580184770[72] = 0;
   out_1214373718580184770[73] = 0;
   out_1214373718580184770[74] = 0;
   out_1214373718580184770[75] = 0;
   out_1214373718580184770[76] = 0;
   out_1214373718580184770[77] = 0;
   out_1214373718580184770[78] = 0;
   out_1214373718580184770[79] = 0;
   out_1214373718580184770[80] = 1;
}
void h_25(double *state, double *unused, double *out_1850377977919926149) {
   out_1850377977919926149[0] = state[6];
}
void H_25(double *state, double *unused, double *out_3354258365989550415) {
   out_3354258365989550415[0] = 0;
   out_3354258365989550415[1] = 0;
   out_3354258365989550415[2] = 0;
   out_3354258365989550415[3] = 0;
   out_3354258365989550415[4] = 0;
   out_3354258365989550415[5] = 0;
   out_3354258365989550415[6] = 1;
   out_3354258365989550415[7] = 0;
   out_3354258365989550415[8] = 0;
}
void h_24(double *state, double *unused, double *out_8505439987153360673) {
   out_8505439987153360673[0] = state[4];
   out_8505439987153360673[1] = state[5];
}
void H_24(double *state, double *unused, double *out_5531472789596700388) {
   out_5531472789596700388[0] = 0;
   out_5531472789596700388[1] = 0;
   out_5531472789596700388[2] = 0;
   out_5531472789596700388[3] = 0;
   out_5531472789596700388[4] = 1;
   out_5531472789596700388[5] = 0;
   out_5531472789596700388[6] = 0;
   out_5531472789596700388[7] = 0;
   out_5531472789596700388[8] = 0;
   out_5531472789596700388[9] = 0;
   out_5531472789596700388[10] = 0;
   out_5531472789596700388[11] = 0;
   out_5531472789596700388[12] = 0;
   out_5531472789596700388[13] = 0;
   out_5531472789596700388[14] = 1;
   out_5531472789596700388[15] = 0;
   out_5531472789596700388[16] = 0;
   out_5531472789596700388[17] = 0;
}
void h_30(double *state, double *unused, double *out_9037330882377984478) {
   out_9037330882377984478[0] = state[4];
}
void H_30(double *state, double *unused, double *out_1173437964138057783) {
   out_1173437964138057783[0] = 0;
   out_1173437964138057783[1] = 0;
   out_1173437964138057783[2] = 0;
   out_1173437964138057783[3] = 0;
   out_1173437964138057783[4] = 1;
   out_1173437964138057783[5] = 0;
   out_1173437964138057783[6] = 0;
   out_1173437964138057783[7] = 0;
   out_1173437964138057783[8] = 0;
}
void h_26(double *state, double *unused, double *out_4407739923670721493) {
   out_4407739923670721493[0] = state[7];
}
void H_26(double *state, double *unused, double *out_387244952884505809) {
   out_387244952884505809[0] = 0;
   out_387244952884505809[1] = 0;
   out_387244952884505809[2] = 0;
   out_387244952884505809[3] = 0;
   out_387244952884505809[4] = 0;
   out_387244952884505809[5] = 0;
   out_387244952884505809[6] = 0;
   out_387244952884505809[7] = 1;
   out_387244952884505809[8] = 0;
}
void h_27(double *state, double *unused, double *out_4454783298728623800) {
   out_4454783298728623800[0] = state[3];
}
void H_27(double *state, double *unused, double *out_3348201275938482694) {
   out_3348201275938482694[0] = 0;
   out_3348201275938482694[1] = 0;
   out_3348201275938482694[2] = 0;
   out_3348201275938482694[3] = 1;
   out_3348201275938482694[4] = 0;
   out_3348201275938482694[5] = 0;
   out_3348201275938482694[6] = 0;
   out_3348201275938482694[7] = 0;
   out_3348201275938482694[8] = 0;
}
void h_29(double *state, double *unused, double *out_4611969967079752945) {
   out_4611969967079752945[0] = state[1];
}
void H_29(double *state, double *unused, double *out_663206619823665599) {
   out_663206619823665599[0] = 0;
   out_663206619823665599[1] = 1;
   out_663206619823665599[2] = 0;
   out_663206619823665599[3] = 0;
   out_663206619823665599[4] = 0;
   out_663206619823665599[5] = 0;
   out_663206619823665599[6] = 0;
   out_663206619823665599[7] = 0;
   out_663206619823665599[8] = 0;
}
void h_28(double *state, double *unused, double *out_2606689624252818460) {
   out_2606689624252818460[0] = state[0];
}
void H_28(double *state, double *unused, double *out_1300423651741660652) {
   out_1300423651741660652[0] = 1;
   out_1300423651741660652[1] = 0;
   out_1300423651741660652[2] = 0;
   out_1300423651741660652[3] = 0;
   out_1300423651741660652[4] = 0;
   out_1300423651741660652[5] = 0;
   out_1300423651741660652[6] = 0;
   out_1300423651741660652[7] = 0;
   out_1300423651741660652[8] = 0;
}
void h_31(double *state, double *unused, double *out_8005825173760586278) {
   out_8005825173760586278[0] = state[8];
}
void H_31(double *state, double *unused, double *out_1013453055117857285) {
   out_1013453055117857285[0] = 0;
   out_1013453055117857285[1] = 0;
   out_1013453055117857285[2] = 0;
   out_1013453055117857285[3] = 0;
   out_1013453055117857285[4] = 0;
   out_1013453055117857285[5] = 0;
   out_1013453055117857285[6] = 0;
   out_1013453055117857285[7] = 0;
   out_1013453055117857285[8] = 1;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_25, H_25, NULL, in_z, in_R, in_ea, MAHA_THRESH_25);
}
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<2, 3, 0>(in_x, in_P, h_24, H_24, NULL, in_z, in_R, in_ea, MAHA_THRESH_24);
}
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_30, H_30, NULL, in_z, in_R, in_ea, MAHA_THRESH_30);
}
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_26, H_26, NULL, in_z, in_R, in_ea, MAHA_THRESH_26);
}
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_27, H_27, NULL, in_z, in_R, in_ea, MAHA_THRESH_27);
}
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_29, H_29, NULL, in_z, in_R, in_ea, MAHA_THRESH_29);
}
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_28, H_28, NULL, in_z, in_R, in_ea, MAHA_THRESH_28);
}
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_31, H_31, NULL, in_z, in_R, in_ea, MAHA_THRESH_31);
}
void car_err_fun(double *nom_x, double *delta_x, double *out_5621847562774482709) {
  err_fun(nom_x, delta_x, out_5621847562774482709);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_6433411341470746887) {
  inv_err_fun(nom_x, true_x, out_6433411341470746887);
}
void car_H_mod_fun(double *state, double *out_1549433459195114425) {
  H_mod_fun(state, out_1549433459195114425);
}
void car_f_fun(double *state, double dt, double *out_6294660566595538893) {
  f_fun(state,  dt, out_6294660566595538893);
}
void car_F_fun(double *state, double dt, double *out_1214373718580184770) {
  F_fun(state,  dt, out_1214373718580184770);
}
void car_h_25(double *state, double *unused, double *out_1850377977919926149) {
  h_25(state, unused, out_1850377977919926149);
}
void car_H_25(double *state, double *unused, double *out_3354258365989550415) {
  H_25(state, unused, out_3354258365989550415);
}
void car_h_24(double *state, double *unused, double *out_8505439987153360673) {
  h_24(state, unused, out_8505439987153360673);
}
void car_H_24(double *state, double *unused, double *out_5531472789596700388) {
  H_24(state, unused, out_5531472789596700388);
}
void car_h_30(double *state, double *unused, double *out_9037330882377984478) {
  h_30(state, unused, out_9037330882377984478);
}
void car_H_30(double *state, double *unused, double *out_1173437964138057783) {
  H_30(state, unused, out_1173437964138057783);
}
void car_h_26(double *state, double *unused, double *out_4407739923670721493) {
  h_26(state, unused, out_4407739923670721493);
}
void car_H_26(double *state, double *unused, double *out_387244952884505809) {
  H_26(state, unused, out_387244952884505809);
}
void car_h_27(double *state, double *unused, double *out_4454783298728623800) {
  h_27(state, unused, out_4454783298728623800);
}
void car_H_27(double *state, double *unused, double *out_3348201275938482694) {
  H_27(state, unused, out_3348201275938482694);
}
void car_h_29(double *state, double *unused, double *out_4611969967079752945) {
  h_29(state, unused, out_4611969967079752945);
}
void car_H_29(double *state, double *unused, double *out_663206619823665599) {
  H_29(state, unused, out_663206619823665599);
}
void car_h_28(double *state, double *unused, double *out_2606689624252818460) {
  h_28(state, unused, out_2606689624252818460);
}
void car_H_28(double *state, double *unused, double *out_1300423651741660652) {
  H_28(state, unused, out_1300423651741660652);
}
void car_h_31(double *state, double *unused, double *out_8005825173760586278) {
  h_31(state, unused, out_8005825173760586278);
}
void car_H_31(double *state, double *unused, double *out_1013453055117857285) {
  H_31(state, unused, out_1013453055117857285);
}
void car_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
void car_set_mass(double x) {
  set_mass(x);
}
void car_set_rotational_inertia(double x) {
  set_rotational_inertia(x);
}
void car_set_center_to_front(double x) {
  set_center_to_front(x);
}
void car_set_center_to_rear(double x) {
  set_center_to_rear(x);
}
void car_set_stiffness_front(double x) {
  set_stiffness_front(x);
}
void car_set_stiffness_rear(double x) {
  set_stiffness_rear(x);
}
}

const EKF car = {
  .name = "car",
  .kinds = { 25, 24, 30, 26, 27, 29, 28, 31 },
  .feature_kinds = {  },
  .f_fun = car_f_fun,
  .F_fun = car_F_fun,
  .err_fun = car_err_fun,
  .inv_err_fun = car_inv_err_fun,
  .H_mod_fun = car_H_mod_fun,
  .predict = car_predict,
  .hs = {
    { 25, car_h_25 },
    { 24, car_h_24 },
    { 30, car_h_30 },
    { 26, car_h_26 },
    { 27, car_h_27 },
    { 29, car_h_29 },
    { 28, car_h_28 },
    { 31, car_h_31 },
  },
  .Hs = {
    { 25, car_H_25 },
    { 24, car_H_24 },
    { 30, car_H_30 },
    { 26, car_H_26 },
    { 27, car_H_27 },
    { 29, car_H_29 },
    { 28, car_H_28 },
    { 31, car_H_31 },
  },
  .updates = {
    { 25, car_update_25 },
    { 24, car_update_24 },
    { 30, car_update_30 },
    { 26, car_update_26 },
    { 27, car_update_27 },
    { 29, car_update_29 },
    { 28, car_update_28 },
    { 31, car_update_31 },
  },
  .Hes = {
  },
  .sets = {
    { "mass", car_set_mass },
    { "rotational_inertia", car_set_rotational_inertia },
    { "center_to_front", car_set_center_to_front },
    { "center_to_rear", car_set_center_to_rear },
    { "stiffness_front", car_set_stiffness_front },
    { "stiffness_rear", car_set_stiffness_rear },
  },
  .extra_routines = {
  },
};

ekf_lib_init(car)
